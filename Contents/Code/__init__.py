# -*- coding: utf-8 -*-

### Imports ###
import sys                  # getdefaultencoding, getfilesystemencoding, platform, argv
import os                   # path.abspath, join, dirname
import re                   #
import inspect              # getfile, currentframe
import urllib2              # Python 2.7
import urllib               # Python 2.7 - for urllib.quote/unquote
from   lxml    import etree #
from   io      import open  # open
import hashlib
import unicodedata          # For XML string sanitization

# Python 2/3 compatibility - bytes type
try:
  bytes
except NameError:
  # Python 2: bytes is not defined, use str instead
  bytes = str

###Mini Functions ###
def natural_sort_key     (s):  return [int(text) if text.isdigit() else text for text in re.split(re.compile('([0-9]+)'), str(s).lower())]  ### Avoid 1, 10, 2, 20... #Usage: list.sort(key=natural_sort_key), sorted(list, key=natural_sort_key)

def encode_path_for_os(p):
  """Encode unicode path to UTF-8 bytes for Python 2 os.path operations.
  Python 2's os.path.exists(), os.walk(), etc. don't handle unicode paths well on Linux.
  They try to encode using ASCII which fails for non-ASCII characters.
  This helper encodes unicode paths to UTF-8 bytes for filesystem operations."""
  if p is None:
    return None
  if isinstance(p, unicode):
    return p.encode('utf-8')
  return p

def sanitize_path        (p):
  """Ensure path is unicode and strip control characters. In Python 2, decode bytes to unicode with UTF-8."""
  # First convert to unicode with encoding detection
  if isinstance(p, unicode):
    result = p
  elif isinstance(p, str):
    # Try UTF-8 first (most common on Linux/Mac)
    try:
      result = p.decode('utf-8')
    except UnicodeDecodeError:
      # UTF-8 failed - might be Latin-1 or other encoding
      # Try to detect mojibake: UTF-8 bytes incorrectly decoded as Latin-1
      try:
        # Decode as Latin-1 (never fails), then check if it looks like UTF-8
        latin1_decoded = p.decode('latin-1')

        # If it has many characters in Latin-1 Supplement range (0x80-0xFF),
        # it might be mojibake. Try re-encoding as Latin-1 and decoding as UTF-8
        if sum(1 for c in latin1_decoded if 0x80 <= ord(c) <= 0xFF) > len(latin1_decoded) * 0.3:
          try:
            # Re-encode as Latin-1 and decode as UTF-8
            result = latin1_decoded.encode('latin-1').decode('utf-8')
            Log.Info(u'[sanitize_path] Recovered from Latin-1 mojibake: "{}"'.format(result[:80]))
          except:
            result = latin1_decoded  # Keep Latin-1 if recovery fails
        else:
          result = latin1_decoded  # Looks like valid Latin-1
      except:
        # Last resort: use system filesystem encoding
        try:
          result = p.decode(sys.getfilesystemencoding())
        except:
          # Final fallback: UTF-8 with replacement chars
          result = p.decode('utf-8', errors='replace')
          Log.Info(u'[sanitize_path] Used replacement chars for invalid UTF-8')
  else:
    result = unicode(p) if p is not None else u''

  # Normalize Unicode to NFC (composed form)
  # This ensures é (single char) instead of e + combining acute
  try:
    result = unicodedata.normalize('NFC', result)
  except:
    pass  # If normalization fails, keep original

  # Strip control characters (0x00-0x1F and 0x7F-0x9F) including newlines, NULL bytes
  # This prevents XML serialization errors in Plex
  cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', result)

  # Log if control characters were removed
  if cleaned != result:
    stripped_count = len(result) - len(cleaned)
    Log.Info(u'[sanitize_path] Stripped {} control char(s): before_len={}, after_len={}, sample: "{}"'.format(
      stripped_count, len(result), len(cleaned), cleaned[:80] if len(cleaned) > 80 else cleaned))

  return cleaned

def sanitize_description(text):
  """Sanitize text descriptions while preserving newlines. Used for summaries and descriptions."""
  if text is None:
    return u''

  # First apply sanitize_path to get unicode and handle encoding
  # But we'll need to restore newlines after
  original_newlines = text.count('\n') if isinstance(text, unicode) else 0

  # Convert to unicode if needed
  if isinstance(text, unicode):
    result = text
  elif isinstance(text, str):
    try:
      result = text.decode('utf-8')
    except:
      try:
        result = text.decode('latin-1')
      except:
        result = unicode(text, errors='replace')
  else:
    result = unicode(text) if text is not None else u''

  # Normalize Unicode
  try:
    result = unicodedata.normalize('NFC', result)
  except:
    pass

  # Strip control characters EXCEPT newlines (0x0A) and carriage returns (0x0D)
  # Remove: 0x00-0x09, 0x0B-0x0C, 0x0E-0x1F, 0x7F-0x9F
  cleaned = re.sub(r'[\x00-\x09\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', result)

  return cleaned

def sanitize_xml_string(s):
  """Sanitize string for use in XML attributes. Removes invalid XML characters and normalizes Unicode."""
  if s is None:
    return ''

  # Convert to string if not already
  if not isinstance(s, (str, unicode)):
    s = unicode(s)

  # Ensure unicode
  # In Python 2, str is bytes and needs decoding
  # In Python 3, str is already unicode (no decode method)
  if isinstance(s, str) and hasattr(str, 'decode'):
    # Python 2: str has decode method
    try:
      s = s.decode('utf-8')
    except:
      s = s.decode('utf-8', errors='replace')
  elif isinstance(s, str):
    # Python 3: str is already unicode, no decoding needed
    pass

  # Filter out invalid XML characters
  # Valid XML chars: #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]
  valid_chars = []
  # Convert to list to work around RestrictedPython sandbox blocking __iter__
  for c in list(s):
    code = ord(c)
    # Allow: tab(9), newline(10), carriage return(13), and printable chars
    if code == 0x09 or code == 0x0A or code == 0x0D or \
       (0x20 <= code <= 0xD7FF) or \
       (0xE000 <= code <= 0xFFFD):
      # Skip forbidden Unicode sequences
      if code not in (0xFFFE, 0xFFFF, 0x2028, 0x2029):
        valid_chars.append(c)

  result = u''.join(valid_chars)

  # Normalize to NFC form
  result = unicodedata.normalize('NFC', result)

  return result

def is_vk_video(video_id):
  """Detect if video ID is from VK (format: -219482354_456239560)."""
  if not video_id:
    return False
  # VK format: negative_number_number (e.g., -219482354_456239560)
  return bool(re.match(r'^-\d+_\d+$', str(video_id)))

def get_vk_channel_avatar(video_url, channel_url):
  """Scrape channel avatar and cover image from VK pages.

  For channel URLs (vkvideo.ru), follows redirects to get anonymous token cookies,
  then retries the original URL with cookies.

  Args:
    video_url: VK video URL (e.g., "https://vk.com/video-219482354_456239560")
    channel_url: VK channel URL (e.g., "https://vkvideo.ru/@public219482354")

  Returns:
    Tuple (avatar_url, cover_url) or (avatar_url, None) or (None, None) if not found
  """
  # Try channel URL first (requires cookie handling)
  if channel_url:
    try:
      Log.Info(u'[VK] Fetching avatar from channel page: {}'.format(channel_url))

      # Build request with Chrome User-Agent
      headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
      }

      # First attempt - this will redirect to get_anonym_token and set cookies
      try:
        html = HTTP.Request(channel_url, headers=headers, cacheTime=0).content

        # Decode bytes to string
        if isinstance(html, bytes):
          html = html.decode('utf-8', errors='ignore')

        # Extract og:image meta tag for avatar
        avatar_url = None
        cover_url = None

        og_image_match = re.search(r'property="og:image"\s+content="([^"]+)"', html)
        if not og_image_match:
          # Try reversed pattern
          og_image_match = re.search(r'content="([^"]+)"\s+property="og:image"', html)

        if og_image_match:
          avatar_url = og_image_match.group(1)
          # Decode HTML entities (&amp; -> &, etc.)
          try:
            import HTMLParser as hp
            avatar_url = hp.HTMLParser().unescape(avatar_url)
          except:
            try:
              import html as html_lib
              avatar_url = html_lib.unescape(avatar_url)
            except:
              pass  # Keep original if unescape fails
          Log.Info(u'[VK] Found channel avatar via og:image from channel page: {}'.format(avatar_url[:80]))

        # Extract channel cover image from Cover__coverImg class or InfoModal__description
        # Try multiple patterns for cover image
        cover_url = None

        # Pattern 1: Cover__coverImg with background-image
        cover_match = re.search(r'class="Cover__coverImg[^"]*"\s+style="background-image:\s*url\(([^)]+)\)"', html)
        if cover_match:
          cover_url = cover_match.group(1).strip('"\'')
          Log.Info(u'[VK] Found cover via Cover__coverImg class')

        # Pattern 2: InfoModal__description or any div with background-image containing userapi
        if not cover_url:
          cover_match = re.search(r'class="[^"]*InfoModal[^"]*"\s+[^>]*style="[^"]*background-image:\s*url\(([^)]+)\)"', html)
          if cover_match:
            cover_url = cover_match.group(1).strip('"\'')
            Log.Info(u'[VK] Found cover via InfoModal class')

        # Pattern 3: Any element with large userapi.com image
        if not cover_url:
          cover_match = re.search(r'https://sun\d+-\d+\.userapi\.com/[^"\s]+(?:1920|1080|cover|banner)[^"\s]*\.jpg', html)
          if cover_match:
            cover_url = cover_match.group(0)
            Log.Info(u'[VK] Found cover via large userapi image pattern')

        # Decode HTML entities if found
        if cover_url:
          try:
            import HTMLParser as hp
            cover_url = hp.HTMLParser().unescape(cover_url)
          except:
            try:
              import html as html_lib
              cover_url = html_lib.unescape(cover_url)
            except:
              pass
          Log.Info(u'[VK] Found channel cover image from channel page: {}'.format(cover_url[:80]))

        if avatar_url or cover_url:
          return (avatar_url, cover_url)

      except Exception as e:
        Log.Info(u'[VK] Channel page request failed (may need cookies): {}'.format(e))

    except Exception as e:
      Log.Info(u'[VK] Could not fetch avatar from channel page: {}'.format(e))

  # Fallback: Try video URL (only provides avatar, no cover)
  if video_url:
    try:
      Log.Info(u'[VK] Fetching avatar from video page: {}'.format(video_url))
      headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
      }
      html = HTTP.Request(video_url, headers=headers, cacheTime=CACHE_1MONTH).content

      # Decode bytes to string
      if isinstance(html, bytes):
        html = html.decode('utf-8', errors='ignore')

      # Extract og:image meta tag
      og_image_match = re.search(r'property="og:image"\s+content="([^"]+)"', html)
      if not og_image_match:
        # Try reversed pattern
        og_image_match = re.search(r'content="([^"]+)"\s+property="og:image"', html)

      if og_image_match:
        avatar_url = og_image_match.group(1)
        # Decode HTML entities
        try:
          import HTMLParser as hp
          avatar_url = hp.HTMLParser().unescape(avatar_url)
        except:
          try:
            import html as html_lib
            avatar_url = html_lib.unescape(avatar_url)
          except:
            pass
        Log.Info(u'[VK] Found channel avatar via og:image from video page: {}'.format(avatar_url[:80]))
        return (avatar_url, None)  # Video page has no cover image

    except Exception as e:
      Log.Info(u'[VK] Could not fetch avatar from video page: {}'.format(e))

  Log.Info(u'[VK] No channel avatar found from any VK page')
  return (None, None)

def js_int               (i):  return int(''.join([x for x in list(i or '0') if x.isdigit()]))  # js-like parseInt - https://gist.github.com/douglasmiranda/2174255

### Return dict value if all fields exists "" otherwise (to allow .isdigit()), avoid key errors
def Dict(var, *arg, **kwarg):  #Avoid TypeError: argument of type 'NoneType' is not iterable
  """ Return the value of an (imbricated) dictionnary, return "" if doesn't exist unless "default=new_value" specified as end argument
      Ex: Dict(variable_dict, 'field1', 'field2', default = 0)
  """
  for key in arg:
    if isinstance(var, dict) and key and key in var or isinstance(var, list) and isinstance(key, int) and 0<=key<len(var):  var = var[key]
    else:  return kwarg['default'] if kwarg and 'default' in kwarg else ""   # Allow Dict(var, tvdbid).isdigit() for example
  return kwarg['default'] if var in (None, '', 'N/A', 'null') and kwarg and 'default' in kwarg else "" if var in (None, '', 'N/A', 'null') else var

### Used to Convert Crowd Sourced Video Titles to Title Case from Sentence Case
def uppercase_regex(a):
    return a.group(1) + a.group(2).upper()

def titlecase(input_string):
    return re.sub(r"(^|\s)(\S)", uppercase_regex, input_string)

### These calls use DeArrow Created By Ajay Ramachandran to Obtain a Crowd Sourced Video Title
def DeArrow(video_id):
  api_url = 'https://sponsor.ajay.app'

  hash = hashlib.sha256(video_id.encode('ascii')).hexdigest()
  
  # DeArrow API recommends using first 4 hash characters.
  url = '{api_url}/api/branding/{hash}'.format(api_url = api_url, hash = hash[:4])

  #HTTP.ClearCache()
  HTTP.CacheTime = 0

  crowd_sourced_title = ''
  
  try:
    data_json = JSON.ObjectFromURL(url)
  except:
    Log.Error(u'DeArrow(): Error while loading JSON.ObjectFromURL. URL: '+ url)

  try:
    first_title_obj = data_json[video_id]['titles'][0]
    if (first_title_obj['votes'] >= 0 and first_title_obj['locked'] == False and first_title_obj['original'] == False):
      crowd_sourced_title = titlecase(first_title_obj['title'])
  except:
    Log.Info(u'DeArrow(): No Crowd Sourced Title Found for Video ID: ' + video_id)

  HTTP.CacheTime = CACHE_1MONTH
  
  return crowd_sourced_title

### Convert ISO8601 Duration format into seconds ###
def ISO8601DurationToSeconds(duration):
  try:     match = re.match(r'PT(\d+H)?(\d+M)?(\d+S)?', duration).groups()
  except:  return 0
  else:    return 3600 * js_int(match[0]) + 60 * js_int(match[1]) + js_int(match[2])

### Get media directory ###
def GetMediaDir (media, movie, file=False):
  if movie:  return os.path.dirname(media.items[0].parts[0].file)
  else:
    for s in media.seasons if media else []: # TV_Show:
      for e in media.seasons[s].episodes:
        Log.Info(sanitize_path(media.seasons[s].episodes[e].items[0].parts[0].file))
        return media.seasons[s].episodes[e].items[0].parts[0].file if file else os.path.dirname(media.seasons[s].episodes[e].items[0].parts[0].file)

### Get media root folder ###
def GetLibraryRootPath(dir):
  library, root, path = '', '', ''
  for root in [os.sep.join(dir.split(os.sep)[0:x+2]) for x in range(0, dir.count(os.sep))]:
    if root in PLEX_LIBRARY:
      library = PLEX_LIBRARY[root]
      path    = os.path.relpath(dir, root)
      break
  else:  #401 no right to list libraries (windows)
    Log.Info(u'[!] Library access denied')
    filename = os.path.join(CachePath, '_Logs', '_root_.scanner.log')
    if os.path.isfile(filename):
      Log.Info(u'[!] ASS root scanner file present: "{}"'.format(filename))
      with open(filename, 'r', encoding='utf-8') as file:
        line = file.read()
      for root in [os.sep.join(dir.split(os.sep)[0:x+2]) for x in range(dir.count(os.sep)-1, -1, -1)]:
        if "root: '{}'".format(root) in line:  path = os.path.relpath(dir, root).rstrip('.');  break  #Log.Info(u'[!] root not found: "{}"'.format(root))
      else: path, root = '_unknown_folder', ''
    else:  Log.Info(u'[!] ASS root scanner file missing: "{}"'.format(filename))
  return library, root, path


def youtube_api_key():
  path = os.path.join(PluginDir, "youtube-key.txt")
  if os.path.isfile(path):
    value = Data.Load(path)
    if value:
      value = value.strip()
    if value:
      Log.Debug(u"Loaded token from youtube-token.txt file")

      return value

  # Fall back to Library preference
  return Prefs['YouTube-Agent_youtube_api_key']


###
def json_load(template, *args):
  url = template.format(*args + tuple([youtube_api_key()]))
  url = sanitize_path(url)
  iteration = 0
  json_page = {}
  json      = {}
  while not json or Dict(json_page, 'nextPageToken') and Dict(json_page, 'pageInfo', 'resultsPerPage') !=1 and iteration<50:
    #Log.Info(u'{}'.format(Dict(json_page, 'pageInfo', 'resultsPerPage')))
    try:                    json_page = JSON.ObjectFromURL(url+'&pageToken='+Dict(json_page, 'nextPageToken') if Dict(json_page, 'nextPageToken') else url)  #Log.Info(u'items: {}'.format(len(Dict(json_page, 'items'))))
    except Exception as e:  json = JSON.ObjectFromString(e.content);  raise ValueError('code: {}, message: {}'.format(Dict(json, 'error', 'code'), Dict(json, 'error', 'message')))
    if json:  json ['items'].extend(json_page['items'])
    else:     json = json_page
    iteration +=1
  #Log.Info(u'total items: {}'.format(len(Dict(json, 'items'))))
  return json

### load image if present in local dir
def img_load(series_root_folder, filename):
  Log(u'img_load() - series_root_folder: {}, filename: {}'.format(series_root_folder, filename))
  for ext in ['jpg', 'jpeg', 'png', 'tiff', 'gif', 'jp2']:
    filename = os.path.join(series_root_folder, filename.rsplit('.', 1)[0]+"."+ext)
    if os.path.isfile(filename):  Log(u'local thumbnail found for file %s', filename);  return filename, Core.storage.load(filename)
  return "", None

### get biggest thumbnail available
def get_thumb(json_video_details):
  # Try VK format first (single 'thumbnail' string)
  vk_thumb = Dict(json_video_details, 'thumbnail')
  if vk_thumb:
    Log.Info(u'[get_thumb] VK thumbnail found: {}'.format(vk_thumb[:80]))
    return vk_thumb

  # Try YouTube format ('thumbnails' array)
  thumbnails = Dict(json_video_details, 'thumbnails')
  if thumbnails:
    for thumbnail in reversed(thumbnails):
      Log.Info(u'[get_thumb] YouTube thumbnail found: {}'.format(thumbnail['url'][:80]))
      return thumbnail['url']

  Log.Error(u'get_thumb(): No thumb found')
  return None

def Start():
  HTTP.CacheTime                  = CACHE_1MONTH
  HTTP.Headers['User-Agent'     ] = 'Mozilla/5.0 (iPad; CPU OS 7_0_4 like Mac OS X) AppleWebKit/537.51.1 (KHTML, like Gecko) Version/7.0 Mobile/11B554a Safari/9537.54'
  HTTP.Headers['Accept-Language'] = 'en-us'

### Assign unique ID ###
def Search(results, media, lang, manual, movie):
  
  displayname = sanitize_path(os.path.basename((media.name if movie else media.show) or "") )
  filename    = media.items[0].parts[0].file if movie else media.filename or media.show
  dir         = GetMediaDir(media, movie)

  # Sanitize filename early to ensure it's unicode and avoid Unicode/ASCII mixing errors
  filename = sanitize_path(filename) if filename else u''
  dir = sanitize_path(dir) if dir else u''

  Log.Info(u'[DEBUG] Raw filename from Plex: len={}, sample: "{}"'.format(
    len(filename) if filename else 0, filename[:100] if filename and len(filename) > 100 else filename))

  # URL decode - filename is already unicode from sanitize_path()
  try:
    if filename:
      # In Python 2, urllib.unquote expects bytes, in Python 3 it can handle str
      try:
        # Try Python 3 style (str input)
        from urllib.parse import unquote
        filename = unquote(filename)
      except ImportError:
        # Python 2: convert to bytes, unquote, then back to unicode
        if isinstance(filename, unicode):
          filename = urllib.unquote(filename.encode('utf-8')).decode('utf-8')
        else:
          filename = urllib.unquote(filename).decode('utf-8')
  except Exception as e:
    Log(u'search() - Exception1: filename: "{}", e: "{}"'.format(filename, e))
    filename = filename or u''

  try:
    filename = os.path.basename(filename) if filename else u''
  except Exception as e:
    Log(u'search() - Exception2: filename: "{}", e: "{}"'.format(filename, e))
    filename = filename or u''

  # Ensure we have valid values
  if not filename or not dir:
    Log.Info(u'search() - Missing required values: filename="{}", dir="{}"'.format(filename, dir))
    return

  Log(u''.ljust(157, '='))
  Log(u"Search() - dir: {}, filename: {}, displayname: {}".format(dir, filename, displayname))
    
  try:
    for regex, url in [('PLAYLIST', YOUTUBE_PLAYLIST_REGEX), ('CHANNEL', YOUTUBE_CHANNEL_REGEX), ('VIDEO', YOUTUBE_VIDEO_REGEX)]:
      result = url.search(filename)
      if result:
        guid = result.group('id')
        Log.Info(u'search() - YouTube ID found - regex: {}, youtube ID: "{}", matched: "{}"'.format(regex, guid, result.group(0)))
        safe_id = sanitize_xml_string('youtube|{}|{}'.format(guid, os.path.basename(dir)))
        results.Append( MetadataSearchResult( id=safe_id, name=displayname, year=None, score=100, lang=lang ) )
        Log(u''.ljust(157, '='))
        return
      else: Log.Info(u'search() - YouTube ID not found - regex: "{}", filename_len: {}, filename_sample: "{}"'.format(regex, len(filename), filename[:100] if len(filename) > 100 else filename))
  except Exception as e:  Log(u'search() - filename: "{}" Regex failed to find YouTube id, error: "{}"'.format(filename, e))
  
  if movie:  Log.Info(filename)
  else:
    s = media.seasons.keys()[0] if media.seasons.keys()[0]!='0' else media.seasons.keys()[1] if len(media.seasons.keys()) >1 else None
    if s:
      result = YOUTUBE_PLAYLIST_REGEX.search(os.path.basename(os.path.dirname(dir)))
      guid   = result.group('id') if result else ''
      youtube_id_path = os.path.join(dir, 'youtube.id')
      # Encode to UTF-8 for Python 2 os.path.exists() compatibility
      if isinstance(youtube_id_path, unicode):
        youtube_id_path = youtube_id_path.encode('utf-8')
      if result or os.path.exists(youtube_id_path):
        Log(u'search() - filename: "{}", found season YouTube playlist id, result.group("id"): {}'.format(filename, result.group('id')))
        safe_id = sanitize_xml_string('youtube|{}|{}'.format(guid, dir))
        results.Append( MetadataSearchResult( id=safe_id, name=filename, year=None, score=100, lang=lang ) )
        Log(u''.ljust(157, '='))
        return
      else:  Log('search() - id not found')
  
  ### Try loading local JSON file if present
  json_filename = os.path.join(dir, os.path.splitext(filename)[0]+ ".info.json")
  Log(u'Searching for info file: {}'.format(json_filename))
  if os.path.exists(encode_path_for_os(json_filename)):
    try:
      with open(encode_path_for_os(json_filename), 'r', encoding='utf-8') as f:
        json_video_details = JSON.ObjectFromString(f.read())
    except Exception as e:
      Log('search() - Unable to load info.json, e: "{}"'.format(e))
    else:
      video_id = Dict(json_video_details, 'id')
      Log('search() - Loaded json_video_details: {}'.format(video_id))
      safe_id = sanitize_xml_string('youtube|{}|{}'.format(video_id, os.path.basename(dir)))
      results.Append( MetadataSearchResult( id=safe_id, name=displayname, year=Datetime.ParseDate(Dict(json_video_details, 'upload_date')).year, score=100, lang=lang ) )
      Log(u''.ljust(157, '='))
      return
  
  try:
    json_video_details = json_load(YOUTUBE_VIDEO_SEARCH, String.Quote(filename, usePlus=False))
    if Dict(json_video_details, 'pageInfo', 'totalResults'):
      Log.Info(u'filename: "{}", title:        "{}"'.format(filename, Dict(json_video_details, 'items', 0, 'snippet', 'title')))
      Log.Info(u'filename: "{}", channelTitle: "{}"'.format(filename, Dict(json_video_details, 'items', 0, 'snippet', 'channelTitle')))
      if filename == Dict(json_video_details, 'items', 0, 'snippet', 'channelTitle'):
        Log.Info(u'filename: "{}", found exact matching YouTube title: "{}", description: "{}"'.format(filename, Dict(json_video_details, 'items', 0, 'snippet', 'channelTitle'), Dict(json_video_details, 'items', 0, 'snippet', 'description')))
        safe_id = sanitize_xml_string('youtube|{}|{}'.format(Dict(json_video_details, 'items', 0, 'id', 'channelId'), dir))
        results.Append( MetadataSearchResult( id=safe_id, name=filename, year=None, score=100, lang=lang ) )
        Log(u''.ljust(157, '='))
        return
      else:  Log.Info(u'search() - no id in title nor matching YouTube title: "{}", closest match: "{}", description: "{}"'.format(filename, Dict(json_video_details, 'items', 0, 'snippet', 'channelTitle'), Dict(json_video_details, 'items', 0, 'snippet', 'description')))
    elif 'error' in json_video_details:  Log.Info(u'search() - code: "{}", message: "{}"'.format(Dict(json_video_details, 'error', 'code'), Dict(json_video_details, 'error', 'message')))
  except Exception as e:  Log(u'search() - Could not retrieve data from YouTube for: "{}", Exception: "{}"'.format(filename, e))

  library, root, path = GetLibraryRootPath(dir)
  # Extract show folder name (3rd from end: Show/Season/file.mp4)
  path_parts = path.split(os.sep)
  show_folder = path_parts[-3] if len(path_parts) >= 3 else path_parts[-2] if len(path_parts) >= 2 else path_parts[-1] if path_parts else ''
  Log(u'Putting folder name "{}" as guid since no assign channel id or playlist id was assigned'.format(show_folder))
  safe_id = sanitize_xml_string('youtube|{}|{}'.format(show_folder, dir))
  results.Append( MetadataSearchResult( id=safe_id, name=os.path.basename(filename), year=None, score=80, lang=lang ) )
  Log(''.ljust(157, '='))

### Download metadata using unique ID ###
def Update(metadata, media, lang, force, movie):
  Log(u'=== update(lang={}, force={}, movie={}) ==='.format(lang, force, movie))

  # Sanitize metadata.id to prevent XML serialization errors
  if hasattr(metadata, 'id'):
    metadata.id = sanitize_xml_string(metadata.id)
  temp1, guid, series_folder = metadata.id.split("|")
  dir                        = sanitize_path(GetMediaDir(media, movie))

  # For TV shows: if dir is a season folder, go up one level to get show folder
  if not movie and re.search(r'Season\s+\d{4}', os.path.basename(dir), re.IGNORECASE):
    dir = os.path.dirname(dir)
    Log.Info(u'[Fix] Detected season folder, using show folder: "{}"'.format(dir))

  channel_id                 = guid if guid.startswith('UC') or guid.startswith('HC') else ''
  channel_title              = ""
  json_playlist_details      = {}
  json_playlist_items        = {}
  json_channel_items         = {}
  json_channel_details       = {}
  json_video_details         = {}
  series_folder              = sanitize_path(series_folder)
  if not (len(guid)>2 and guid[0:2] in ('PL', 'UU', 'FL', 'LP', 'RD')):  metadata.title = re.sub(r'\[.*\]', '', os.path.basename(dir)).strip()  #no id mode, update title so ep gets updated
  Log(u''.ljust(157, '='))
    
  ### Movie Library ###
  if movie:

    ### Movie - JSON call ###############################################################################################################
    filename = media.items[0].parts[0].file if movie else media.filename or media.show
    dir = GetMediaDir(media, movie)
    try:                    filename = sanitize_path(filename)
    except Exception as e:  Log('update() - Exception1: filename: "{}", e: "{}"'.format(filename, e))
    try:                    filename = os.path.basename(filename)
    except Exception as e:  Log('update() - Exception2: filename: "{}", e: "{}"'.format(filename, e))
    try:                    filename = urllib.unquote(filename)
    except Exception as e:  Log('update() - Exception3: filename: "{}", e: "{}"'.format(filename, e))

    json_filename = os.path.join(dir, os.path.splitext(filename)[0]+ ".info.json")
    Log(u'Update: Searching for info file: {}, dir:{}'.format(json_filename, GetMediaDir(media, movie, True)))
    if os.path.exists(json_filename):
      try:
        with open(json_filename, 'r', encoding='utf-8') as f:
          json_video_details = JSON.ObjectFromString(f.read())
      except IOError:  guid = None
      else:    
        guid          = Dict(json_video_details, 'id')
        channel_id    = Dict(json_video_details, 'channel_id')

        ### Movie - Local JSON
        Log.Info(u'update() using json file json_video_details - Loaded video details from: "{}"'.format(json_filename))
        metadata.title                   = Dict(json_video_details, 'title');                                  Log(u'series title:       "{}"'.format(Dict(json_video_details, 'title')))
        metadata.summary                 = Dict(json_video_details, 'description');                            Log(u'series description: '+Dict(json_video_details, 'description').replace('\n', '. '))

        if Prefs['use_crowd_sourced_titles'] == True:
          crowd_sourced_title = DeArrow(guid)
          if crowd_sourced_title != '':
            metadata.original_title = metadata.title
            metadata.summary = 'Original Title: ' + metadata.title + '\r\n\r\n' + metadata.summary
            metadata.title = crowd_sourced_title

        metadata.duration                = Dict(json_video_details, 'duration');                               Log(u'series duration:    "{}"->"{}"'.format(Dict(json_video_details, 'duration'), metadata.duration))
        metadata.genres                  = Dict(json_video_details, 'categories');                             Log(u'genres: '+str([x for x in metadata.genres]))
        date                             = Datetime.ParseDate(Dict(json_video_details, 'upload_date'));        Log(u'date:  "{}"'.format(date))
        metadata.originally_available_at = date.date()
        metadata.year                    = date.year  #test avoid:  AttributeError: 'TV_Show' object has no attribute named 'year'
        thumb                            = get_thumb(json_video_details)
        if thumb and thumb not in metadata.posters:
          Log(u'poster: "{}" added'.format(thumb))
          metadata.posters[thumb]        = Proxy.Media(HTTP.Request(thumb).content, sort_order=1)
        else:  Log(u'thumb: "{}" already present'.format(thumb))
        if Dict(json_video_details, 'statistics', 'likeCount') and int(Dict(json_video_details, 'like_count')) > 0 and Dict(json_video_details, 'dislike_count') and int(Dict(json_video_details, 'dislike_count')) > 0:
          metadata.rating                = float(10*int(Dict(json_video_details, 'like_count'))/(int(Dict(json_video_details, 'dislike_count'))+int(Dict(json_video_details, 'like_count'))));  Log(u'rating: {}'.format(metadata.rating))
        if Prefs['add_user_as_director']:
          metadata.directors.clear()
          try:
            director            = Dict(json_video_details, 'uploader');
            meta_director       = metadata.directors.new()
            meta_director.name  = director
            Log('director: '+ director)
          except:  pass
        return

    ### Movie - API call ################################################################################################################
    Log(u'update() using api - guid: {}, dir: {}, metadata.id: {}'.format(guid, dir, metadata.id))
    try:     json_video_details = json_load(YOUTUBE_json_video_details, guid)['items'][0]
    except:  Log(u'json_video_details - Could not retrieve data from YouTube for: ' + guid)
    else:
      Log('Movie mode - json_video_details - Loaded video details from: "{}"'.format(YOUTUBE_json_video_details.format(guid, 'personal_key')))
      date                             = Datetime.ParseDate(json_video_details['snippet']['publishedAt']);  Log('date:  "{}"'.format(date))
      metadata.originally_available_at = date.date()
      metadata.title                   = json_video_details['snippet']['title'];                                                      Log(u'series title:       "{}"'.format(json_video_details['snippet']['title']))
      metadata.summary                 = json_video_details['snippet']['description'];                                                Log(u'series description: '+json_video_details['snippet']['description'].replace('\n', '. '))

      if Prefs['use_crowd_sourced_titles'] == True:
        crowd_sourced_title = DeArrow(guid)
        if crowd_sourced_title != '':
          metadata.original_title = metadata.title
          metadata.summary = 'Original Title: ' + metadata.title + '\r\n\r\n' + metadata.summary
          metadata.title = crowd_sourced_title

      metadata.duration                = ISO8601DurationToSeconds(json_video_details['contentDetails']['duration'])*1000;             Log(u'series duration:    "{}"->"{}"'.format(json_video_details['contentDetails']['duration'], metadata.duration))
      metadata.genres                  = [YOUTUBE_CATEGORY_ID[id] for id in json_video_details['snippet']['categoryId'].split(',')];  Log(u'genres: '+str([x for x in metadata.genres]))
      metadata.year                    = date.year;                                                                              Log(u'movie year: {}'.format(date.year))
      thumb                            = json_video_details['snippet']['thumbnails']['default']['url'];                               Log(u'thumb: "{}"'.format(thumb))
      if thumb and thumb not in metadata.posters:
        Log(u'poster: "{}"'.format(thumb))
        metadata.posters[thumb]        = Proxy.Media(HTTP.Request(Dict(json_video_details, 'snippet', 'thumbnails', 'maxres', 'url') or Dict(json_video_details, 'snippet', 'thumbnails', 'medium', 'url') or Dict(json_video_details, 'snippet', 'thumbnails', 'standard', 'url') or Dict(json_video_details, 'snippet', 'thumbnails', 'high', 'url') or Dict(json_video_details, 'snippet', 'thumbnails', 'default', 'url')).content, sort_order=1)
      if Dict(json_video_details, 'statistics', 'likeCount') and int(json_video_details['statistics']['likeCount']) > 0 and Dict(json_video_details, 'statistics', 'dislikeCount') and int(Dict(json_video_details, 'statistics', 'dislikeCount')) > 0:
        metadata.rating                = float(10*int(json_video_details['statistics']['likeCount'])/(int(json_video_details['statistics']['dislikeCount'])+int(json_video_details['statistics']['likeCount'])));  Log('rating: {}'.format(metadata.rating))
      if Prefs['add_user_as_director']:
        metadata.directors.clear()
        try:
          meta_director       = metadata.directors.new()
          meta_director.name  = json_video_details['snippet']['channelTitle']
          Log(u'director: '+json_video_details['snippet']['channelTitle'])
        except Exception as e:  Log.Info(u'[!] add_user_as_director exception: {}'.format(e))
      return
  
  ### TV series Library ###
  else:
    title=""
    ### Collection tag for grouping folders ###
    library, root, path = GetLibraryRootPath(dir)
    series_root_folder=''
    Log.Info(u'[ ] library:    "{}"'.format(library))
    Log.Info(u'[ ] root:       "{}"'.format(root   ))
    Log.Info(u'[ ] path:       "{}"'.format(path   ))
    Log.Info(u'[ ] dir:        "{}"'.format(dir    ))
    metadata.studio = 'YouTube'
    if not path in ('_unknown_folder', '.'):
      #Log.Info('[ ] series root folder:        "{}"'.format(os.path.join(root, path.split(os.sep, 1)[0])))
      series_root_folder  = os.path.join(root, path.split(os.sep, 1)[0] if os.sep in path else path)
      Log.Info(u'[ ] series_root_folder: "{}"'.format(series_root_folder))
      if os.path.exists(encode_path_for_os(series_root_folder)):
        list_files_raw = os.listdir(encode_path_for_os(series_root_folder))
        # Decode bytes returned by os.listdir() to unicode (Python 2)
        list_files = []
        for f in list_files_raw:
          # Python 2: str is bytes, need to decode
          # Python 3: str is already unicode
          if isinstance(f, bytes):
            list_files.append(f.decode('utf-8'))
          else:
            list_files.append(f)
      else:
        list_files = []
      # Keep paths as unicode, only encode when calling os functions
      subfolder_count = len([file for file in list_files if os.path.isdir(encode_path_for_os(os.path.join(series_root_folder, file)))])
      Log.Info(u'[ ] subfolder_count:    "{}"'.format(subfolder_count   ))

      ### Extract season and transparent folder to reduce complexity and use folder as serie name ###
      reverse_path, season_folder_first = list(reversed(path.split(os.sep))), False
      SEASON_RX = [ r'^Specials',                                                                                                                                           # Specials (season 0)
                    r'^(?P<show>.*)?[\._\-\— ]*?(Season|Series|Book|Saison|Livre|Temporada|[Ss])[\._\—\- ]*?(?P<season>\d{1,4}).*?',                                        # (title) S01
                    r'^(?P<show>.*)?[\._\-\— ]*?Volume[\._\-\— ]*?(?P<season>(?=[MDCLXVI])M*D?C{0,4}L?X{0,4}V?I{0,4}).*?',                                                  # (title) S01
                    r'^(Saga|(Story )?Ar[kc])']                                                                                                                             # Last entry, folder name droped but files kept: Saga / Story Ar[kc] / Ar[kc]
      for folder in reverse_path[:-1]:                 # remove root folder from test, [:-1] Doesn't thow errors but gives an empty list if items don't exist, might not be what you want in other cases
        for rx in SEASON_RX[:-1]:                      # in anime, more specials folders than season folders, so doing it first
          if re.match(rx, folder, re.IGNORECASE):      # get season number but Skip last entry in seasons (skipped folders)
            reverse_path.remove(folder)                # Since iterating slice [:] or [:-1] doesn't hinder iteration. All ways to remove: reverse_path.pop(-1), reverse_path.remove(thing|array[0])
            if rx!=SEASON_RX[-1] and len(reverse_path)>=2 and folder==reverse_path[-2]:  season_folder_first = True
            break

      if len(reverse_path)>1 and not season_folder_first and subfolder_count>1:  ### grouping folders only ###
        Log.Info("Grouping folder found, root: {}, path: {}, Grouping folder: {}, subdirs: {}, reverse_path: {}".format(root, path, os.path.basename(series_root_folder), subfolder_count, reverse_path))
        collection = re.sub(r'\[.*\]', '', reverse_path[-1]).strip()
        Log.Info('[ ] collections:        "{}"'.format(collection))
        if collection not in metadata.collections:  metadata.collections=[collection]
      else:  Log.Info(u"Grouping folder not found or single folder, root: {}, path: {}, Grouping folder: {}, subdirs: {}, reverse_path: {}".format(root, path, os.path.basename(series_root_folder), subfolder_count, reverse_path))

    ### Series - Playlist ###############################################################################################################
    if len(guid)>2 and guid[0:2] in ('PL', 'UU', 'FL', 'LP', 'RD'):
      Log.Info('[?] json_playlist_details')
      try:                    json_playlist_details = json_load(YOUTUBE_PLAYLIST_DETAILS, guid)['items'][0]
      except Exception as e:  Log('[!] json_playlist_details exception: {}, url: {}'.format(e, YOUTUBE_PLAYLIST_DETAILS.format(guid, 'personal_key')))
      else:
        Log.Info('[?] json_playlist_details: {}'.format(json_playlist_details.keys()))
        channel_id                       = Dict(json_playlist_details, 'snippet', 'channelId');                               Log.Info('[ ] channel_id: "{}"'.format(channel_id))
        title                            = sanitize_path(Dict(json_playlist_details, 'snippet', 'title'));                    Log.Info('[ ] title:      "{}"'.format(metadata.title))
        if title: metadata.title = title
        metadata.originally_available_at = Datetime.ParseDate(Dict(json_playlist_details, 'snippet', 'publishedAt')).date();  Log.Info('[ ] publishedAt:  {}'.format(Dict(json_playlist_details, 'snippet', 'publishedAt' )))
        metadata.summary                 = Dict(json_playlist_details, 'snippet', 'description');                             Log.Info('[ ] summary:     "{}"'.format((Dict(json_playlist_details, 'snippet', 'description').replace('\n', '. '))))

        if Prefs['use_crowd_sourced_titles'] == True:
          crowd_sourced_title = DeArrow(guid)
          if crowd_sourced_title != '':
            metadata.summary = 'Original Title: ' + metadata.title + '\r\n\r\n' + metadata.summary
            metadata.title = crowd_sourced_title

      Log.Info('[?] json_playlist_items')
      try:                    json_playlist_items = json_load(YOUTUBE_PLAYLIST_ITEMS, guid)
      except Exception as e:  Log.Info('[!] json_playlist_items exception: {}, url: {}'.format(e, YOUTUBE_PLAYLIST_ITEMS.format(guid, 'personal_key')))
      else:
        Log.Info('[?] json_playlist_items: {}'.format(json_playlist_items.keys()))
        first_video = sorted(Dict(json_playlist_items, 'items'), key=lambda i: Dict(i, 'contentDetails', 'videoPublishedAt'))[0]
        thumb = Dict(first_video, 'snippet', 'thumbnails', 'maxres', 'url') or Dict(first_video, 'snippet', 'thumbnails', 'medium', 'url') or Dict(first_video, 'snippet', 'thumbnails', 'standard', 'url') or Dict(first_video, 'snippet', 'thumbnails', 'high', 'url') or Dict(first_video, 'snippet', 'thumbnails', 'default', 'url')
        if thumb and thumb not in metadata.posters:  Log('[ ] posters:   {}'.format(thumb));  metadata.posters [thumb] = Proxy.Media(HTTP.Request(thumb).content, sort_order=1 if Prefs['media_poster_source']=='Episode' else 2)
        else:                                        Log('[X] posters:   {}'.format(thumb))
    
    ### Series - Channel ###############################################################################################################
    if channel_id.startswith('UC') or channel_id.startswith('HC'):
      try:
        json_channel_details  = json_load(YOUTUBE_CHANNEL_DETAILS, channel_id)['items'][0]
        json_channel_items    = json_load(YOUTUBE_CHANNEL_ITEMS, channel_id)
      except Exception as e:  Log('exception: {}, url: {}'.format(e, guid))
      else:
        
        if not title:
          title          = re.sub(r"\s*\[.*?\]\s*"," ",series_folder)  #instead of path use series foldername
          metadata.title = title
        Log.Info('[ ] title:        "{}", metadata.title: "{}"'.format(title, metadata.title))
        if not Dict(json_playlist_details, 'snippet', 'description'):
          if Dict(json_channel_details, 'snippet', 'description'):  metadata.summary = sanitize_description(Dict(json_channel_details, 'snippet', 'description'))
          else:
            summary  = u'Channel with {} videos, '.format(Dict(json_channel_details, 'statistics', 'videoCount'))
            summary += u'{} subscribers, '.format(Dict(json_channel_details, 'statistics', 'subscriberCount'))
            summary += u'{} views'.format(Dict(json_channel_details, 'statistics', 'viewCount'))
            metadata.summary = summary;  Log.Info(u'[ ] summary:     "{}"'.format(summary))  #

        if Prefs['use_crowd_sourced_titles'] == True:
          crowd_sourced_title = DeArrow(guid)
          if crowd_sourced_title != '':
            metadata.summary = 'Original Title: ' + metadata.title + '\r\n\r\n' + metadata.summary
            metadata.title = crowd_sourced_title

        if Dict(json_channel_details,'snippet','country') and Dict(json_channel_details,'snippet','country') not in metadata.countries:
          metadata.countries.add(Dict(json_channel_details,'snippet','country'));  Log.Info('[ ] country: {}'.format(Dict(json_channel_details,'snippet','country') ))

        ### Playlist with cast coming from multiple chan entries in youtube.id file ###############################################################################################################
        if os.path.exists(os.path.join(dir, 'youtube.id')):
          with open(os.path.join(dir, 'youtube.id'), encoding='utf-8') as f:
            metadata.roles.clear()
            for line in f.readlines():
              try:                    json_channel_details = json_load(YOUTUBE_CHANNEL_DETAILS, line.rstrip())['items'][0]
              except Exception as e:  Log('exception: {}, url: {}'.format(e, guid))
              else:
                Log.Info('[?] json_channel_details: {}'.format(json_channel_details.keys()))
                Log.Info('[ ] title:       "{}"'.format(Dict(json_channel_details, 'snippet', 'title'      )))
                if not Dict(json_playlist_details, 'snippet', 'description'):
                  if Dict(json_channel_details, 'snippet', 'description'):  metadata.summary =  sanitize_description(Dict(json_channel_details, 'snippet', 'description'))
                  #elif guid.startswith('PL'):  metadata.summary = 'No Playlist nor Channel summary'
                  else:
                    summary  = u'Channel with {} videos, '.format(Dict(json_channel_details, 'statistics', 'videoCount'     ))
                    summary += u'{} subscribers, '.format(Dict(json_channel_details, 'statistics', 'subscriberCount'))
                    summary += u'{} views'.format(Dict(json_channel_details, 'statistics', 'viewCount'      ))
                    metadata.summary = summary #or 'No Channel summary'
                    Log.Info(u'[ ] summary:     "{}"'.format(Dict(json_channel_details, 'snippet', 'description').replace('\n', '. ')))  #
                
                if Dict(json_channel_details,'snippet','country') and Dict(json_channel_details,'snippet','country') not in metadata.countries:
                  metadata.countries.add(Dict(json_channel_details,'snippet','country'));  Log.Info('[ ] country: {}'.format(Dict(json_channel_details,'snippet','country') ))
                
                thumb_channel = Dict(json_channel_details, 'snippet', 'thumbnails', 'medium', 'url') or Dict(json_channel_details, 'snippet', 'thumbnails', 'high', 'url')   or Dict(json_channel_details, 'snippet', 'thumbnails', 'default', 'url')
                role       = metadata.roles.new()
                role.role  = sanitize_path(Dict(json_channel_details, 'snippet', 'title'))
                role.name  = sanitize_path(Dict(json_channel_details, 'snippet', 'title'))
                role.photo = thumb_channel
                Log.Info('[ ] role:        {}'.format(Dict(json_channel_details,'snippet','title')))
                
                thumb = Dict(json_channel_details, 'brandingSettings', 'image', 'bannerTvLowImageUrl' ) or Dict(json_channel_details, 'brandingSettings', 'image', 'bannerTvMediumImageUrl') \
                  or Dict(json_channel_details, 'brandingSettings', 'image', 'bannerTvHighImageUrl') or Dict(json_channel_details, 'brandingSettings', 'image', 'bannerTvImageUrl'      )
                external_banner_url = Dict(json_channel_details, 'brandingSettings', 'image', 'bannerExternalUrl')
                if not thumb and external_banner_url: thumb = '{}=s1920'.format(external_banner_url)
                if thumb and thumb not in metadata.art:      Log('[X] art:       {}'.format(thumb));  metadata.art [thumb] = Proxy.Media(HTTP.Request(thumb).content, sort_order=1)
                else:                                        Log('[ ] art:       {}'.format(thumb))
                if thumb and thumb not in metadata.banners:  Log('[X] banners:   {}'.format(thumb));  metadata.banners [thumb] = Proxy.Media(HTTP.Request(thumb).content, sort_order=1)
                else:                                        Log('[ ] banners:   {}'.format(thumb))
                if thumb_channel and thumb_channel not in metadata.posters:
                  Log('[X] posters:   {}'.format(thumb_channel))
                  metadata.posters [thumb_channel] = Proxy.Media(HTTP.Request(thumb_channel).content, sort_order=1 if Prefs['media_poster_source']=='Channel' else 2)
                  #metadata.posters.validate_keys([thumb_channel])
                else:                                                        Log('[ ] posters:   {}'.format(thumb_channel))
        
        ### Cast comes from channel
        else:    
          thumb         = Dict(json_channel_details, 'brandingSettings', 'image', 'bannerTvLowImageUrl' ) or Dict(json_channel_details, 'brandingSettings', 'image', 'bannerTvMediumImageUrl') \
                       or Dict(json_channel_details, 'brandingSettings', 'image', 'bannerTvHighImageUrl') or Dict(json_channel_details, 'brandingSettings', 'image', 'bannerTvImageUrl'      )
          external_banner_url = Dict(json_channel_details, 'brandingSettings', 'image', 'bannerExternalUrl')
          if not thumb and external_banner_url: thumb = '{}=s1920'.format(external_banner_url)
          if thumb and thumb not in metadata.art:      Log(u'[X] art:       {}'.format(thumb));  metadata.art [thumb] = Proxy.Media(HTTP.Request(thumb).content, sort_order=1)
          else:                                        Log(u'[ ] art:       {}'.format(thumb))
          if thumb and thumb not in metadata.banners:  Log(u'[X] banners:   {}'.format(thumb));  metadata.banners [thumb] = Proxy.Media(HTTP.Request(thumb).content, sort_order=1)
          else:                                        Log(u'[ ] banners:   {}'.format(thumb))
          thumb_channel = Dict(json_channel_details, 'snippet', 'thumbnails', 'medium', 'url') or Dict(json_channel_details, 'snippet', 'thumbnails', 'high', 'url')   or Dict(json_channel_details, 'snippet', 'thumbnails', 'default', 'url')
          if thumb_channel and thumb_channel not in metadata.posters:
            #thumb_channel = sanitize_path(thumb_channel)
            Log(u'[X] posters:   {}'.format(thumb_channel))
            metadata.posters [thumb_channel] = Proxy.Media(HTTP.Request(thumb_channel).content, sort_order=1 if Prefs['media_poster_source']=='Channel' else 2)
            #metadata.posters.validate_keys([thumb_channel])
          else:                                        Log('[ ] posters:   {}'.format(thumb_channel))
          metadata.roles.clear()
          role       = metadata.roles.new()
          role.role  = sanitize_path(Dict(json_channel_details, 'snippet', 'title'))
          role.name  = sanitize_path(Dict(json_channel_details, 'snippet', 'title'))
          role.photo = thumb_channel
          Log.Info(u'[ ] role:        {}'.format(Dict(json_channel_details,'snippet','title')))
          #if not Dict(json_playlist_details, 'snippet', 'publishedAt'):  metadata.originally_available_at = Datetime.ParseDate(Dict(json_channel_items, 'snippet', 'publishedAt')).date();  Log.Info('[ ] publishedAt:  {}'.format(Dict(json_channel_items, 'snippet', 'publishedAt' )))
           
    #NOT PLAYLIST NOR CHANNEL GUID
    else:
      Log.Info('No GUID so random folder')
      # Extract show folder from dir path (after season folder fix, dir is "/path/Show Name/")
      dir_parts = dir.rstrip(os.sep).split(os.sep)
      show_name = dir_parts[-1] if len(dir_parts) >= 1 else series_folder
      metadata.title = show_name
      Log.Info(u'Extracted show title from path: "{}"'.format(show_name))
 
    ### Season + Episode loop ###
    genre_array = {}
    episodes    = 0

    for s in sorted(media.seasons, key=natural_sort_key):
      Log.Info(u"".ljust(157, '='))
      Log.Info(u"Season: {:>2}".format(s))
    
      for e in sorted(media.seasons[s].episodes, key=natural_sort_key):
        filename  = sanitize_path(os.path.basename(media.seasons[s].episodes[e].items[0].parts[0].file))
        episode   = metadata.seasons[s].episodes[e]
        episodes += 1
        Log.Info('metadata.seasons[{:>2}].episodes[{:>3}] "{}"'.format(s, e, filename))
        
        for video in Dict(json_playlist_items, 'items') or Dict(json_channel_items, 'items') or {}:
          
          # videoId in Playlist/channel
          videoId = Dict(video, 'id', 'videoId') or Dict(video, 'snippet', 'resourceId', 'videoId')
          if videoId and videoId in filename:
            episode.title                   = sanitize_path(Dict(video, 'snippet', 'title'       ));                                                                  Log.Info(u'[ ] title:        {}'.format(Dict(video, 'snippet', 'title'       )))
            # Add video URL to episode summary with newlines preserved
            # Playlist/channel videos are always YouTube
            video_url = u'https://www.youtube.com/watch?v={}'.format(videoId)
            video_desc = sanitize_description(Dict(video, 'snippet', 'description'))
            episode.summary = u'Video URL: {}\n\n{}'.format(video_url, video_desc)
            Log.Info(u'[ ] description:  {}'.format(Dict(video, 'snippet', 'description' ).replace('\n', '. ')))
            episode.originally_available_at = Datetime.ParseDate(Dict(video, 'contentDetails', 'videoPublishedAt') or Dict(video, 'snippet', 'publishedAt')).date();  Log.Info('[ ] publishedAt:  {}'.format(Dict(video, 'contentDetails', 'videoPublishedAt' )))
            thumb                           = Dict(video, 'snippet', 'thumbnails', 'maxres', 'url') or Dict(video, 'snippet', 'thumbnails', 'medium', 'url')or Dict(video, 'snippet', 'thumbnails', 'standard', 'url') or Dict(video, 'snippet', 'thumbnails', 'high', 'url') or Dict(video, 'snippet', 'thumbnails', 'default', 'url')
            if thumb and thumb not in episode.thumbs:  episode.thumbs[thumb] = Proxy.Media(HTTP.Request(thumb).content, sort_order=1);                                Log.Info('[ ] thumbnail:    {}'.format(thumb))
            Log.Info(u'[ ] channelTitle: {}'.format(Dict(video, 'snippet', 'channelTitle')))
            break
        
        else:  # videoId not in Playlist/channel item list

          #Loading json file if available
          json_filename = filename.rsplit('.', 1)[0] + ".info.json"
          Log.Info(u'populate_episode_metadata_from_info_json() - series_root_folder: {}, filename: {}'.format(series_root_folder, filename))
          Log.Info(u'Searching for "{}". Searching in "{}".'.format(json_filename, series_root_folder))
          for root, dirnames, filenames in os.walk(encode_path_for_os(series_root_folder)):
            # Decode root if it's bytes (Python 2 returns bytes when given bytes)
            if isinstance(root, bytes):
              root = root.decode('utf-8')
            Log.Info(u'Directory {} contains {} files'.format(root, len(filenames)))  #for filename in filenames: Log.Info('File: {}'.format(filename))

            # Normalize all filenames to NFC to match our normalized json_filename
            # Keep mapping from normalized to original for file access
            normalized_to_original = {}
            for fn in filenames:
              # Convert to unicode if it's bytes (Python 2 with byte paths)
              if isinstance(fn, bytes):
                fn_unicode = fn.decode('utf-8')
              else:
                # Python 3: already str (unicode), or Python 2 with unicode paths
                fn_unicode = fn
              # Normalize to NFC and keep original for file access
              normalized_to_original[unicodedata.normalize('NFC', fn_unicode)] = fn

            if json_filename in normalized_to_original :
              # Use the original filename from filesystem for file access
              original_json_filename = normalized_to_original[json_filename]
              # Build path - original_json_filename might be bytes (Python 2) or str (Python 3)
              # Convert to unicode for joining with root (which is already unicode)
              if isinstance(original_json_filename, bytes):
                original_json_filename_unicode = original_json_filename.decode('utf-8')
              else:
                original_json_filename_unicode = original_json_filename

              json_file = os.path.join(root, original_json_filename_unicode)
              try:
                # Encode path for filesystem operations (Python 2 compatibility)
                with open(encode_path_for_os(json_file), 'r', encoding='utf-8') as f:
                  json_video_details = JSON.ObjectFromString(f.read())
              except: json_video_details = None
              if json_video_details:
                Log.Info('Attempting to read metadata from {}'.format(os.path.join(root, json_filename)))
                videoId = Dict(json_video_details, 'id')
                Log.Info('# videoId [{}] not in Playlist/channel item list so loading json_video_details'.format(videoId))

                # Detect VK video and extract channel metadata
                if is_vk_video(videoId):
                  Log.Info('[VK] VK video detected: {}'.format(videoId))
                  uploader = Dict(json_video_details, 'uploader')
                  uploader_id = Dict(json_video_details, 'uploader_id')
                  webpage_url = Dict(json_video_details, 'webpage_url')

                  # Build VK channel URL
                  if uploader_id:
                    group_id = uploader_id.replace('-', '')
                    channel_url = u'https://vkvideo.ru/@public{}'.format(group_id)
                    Log.Info('[VK] Channel URL: {}'.format(channel_url))

                    # Add channel info to show metadata (only once)
                    if not metadata.summary and uploader:
                      # Get channel avatar and cover from VK pages (tries channel first, falls back to video)
                      avatar_url, cover_url = get_vk_channel_avatar(webpage_url, channel_url)

                      # Add channel poster (avatar)
                      if avatar_url:
                        Log.Info('[VK] Channel avatar found (full URL): {}'.format(avatar_url))
                        if avatar_url not in metadata.posters:
                          try:
                            metadata.posters[avatar_url] = Proxy.Media(HTTP.Request(avatar_url).content, sort_order=1)
                            Log.Info('[VK] Added channel poster from og:image')
                          except Exception as e:
                            Log.Error('[VK] Failed to fetch avatar: {}'.format(e))
                      else:
                        # Fallback: Use video thumbnail as channel poster
                        vk_thumb = Dict(json_video_details, 'thumbnail')
                        if vk_thumb:
                          Log.Info('[VK] Using video thumbnail as channel poster (fallback): {}'.format(vk_thumb[:80]))
                          if vk_thumb not in metadata.posters:
                            try:
                              metadata.posters[vk_thumb] = Proxy.Media(HTTP.Request(vk_thumb).content, sort_order=1)
                              Log.Info('[VK] Added channel poster from video thumbnail (fallback)')
                            except Exception as e:
                              Log.Error('[VK] Failed to fetch video thumbnail: {}'.format(e))

                      # Add channel cover/banner as background art
                      if cover_url:
                        Log.Info('[VK] Channel cover found: {}'.format(cover_url[:80]))
                        if cover_url not in metadata.art:
                          try:
                            metadata.art[cover_url] = Proxy.Media(HTTP.Request(cover_url).content, sort_order=1)
                            Log.Info('[VK] Added channel cover as background art')
                          except Exception as e:
                            Log.Error('[VK] Failed to fetch cover: {}'.format(e))

                      # Set channel description with URL
                      channel_desc = u'VK Channel: {}\nChannel URL: {}'.format(uploader, channel_url)
                      metadata.summary = channel_desc
                      Log.Info('[VK] Set channel summary: {}'.format(uploader))

                  Log.Info('[?] link:     "{}"'.format(webpage_url or videoId))
                else:
                  Log.Info('[?] link:     "https://www.youtube.com/watch?v={}"'.format(videoId))
                thumb, picture = img_load(series_root_folder, filename)  #Load locally
                if not thumb:  # Check for None or empty string
                  thumb = get_thumb(json_video_details)
                  if thumb and thumb not in episode.thumbs:
                    picture = HTTP.Request(thumb).content
                if thumb and thumb not in episode.thumbs:
                  Log.Info(u'[ ] thumbs:   "{}"'.format(thumb))
                  episode.thumbs[thumb] = Proxy.Media(picture, sort_order=1)
                  episode.thumbs.validate_keys([thumb])
                  
                episode.title                   = sanitize_path(Dict(json_video_details, 'title'));            Log.Info(u'[ ] title:    "{}"'.format(Dict(json_video_details, 'title')))
                # Add video URL and preserve newlines
                video_id = Dict(json_video_details, 'id')
                # Use webpage_url from .info.json if available, otherwise construct URL
                video_url = Dict(json_video_details, 'webpage_url')
                if not video_url:
                  # Fallback: construct URL based on video type
                  if is_vk_video(video_id):
                    video_url = u'https://vk.com/video{}'.format(video_id)
                  else:
                    video_url = u'https://www.youtube.com/watch?v={}'.format(video_id)
                video_desc = sanitize_description(Dict(json_video_details, 'description'))
                episode.summary = u'Video URL: {}\n\n{}'.format(video_url, video_desc)
                Log.Info(u'[ ] summary:  "{}"'.format(Dict(json_video_details, 'description').replace('\n', '. ')))
                if len(str(e))>3: episode.originally_available_at = Datetime.ParseDate(Dict(json_video_details, 'upload_date')).date();  Log.Info(u'[ ] date:     "{}"'.format(Dict(json_video_details, 'upload_date')))
                episode.duration                = int(Dict(json_video_details, 'duration'));                           Log.Info(u'[ ] duration: "{}"'.format(episode.duration))
                if Dict(json_video_details, 'likeCount') and int(Dict(json_video_details, 'like_count')) > 0 and Dict(json_video_details, 'dislike_count') and int(Dict(json_video_details, 'dislike_count')) > 0:
                  episode.rating                = float(10*int(Dict(json_video_details, 'like_count'))/(int(Dict(json_video_details, 'dislike_count'))+int(Dict(json_video_details, 'like_count'))));  Log('[ ] rating:   "{}"'.format(episode.rating))
                if channel_title and channel_title not in [role_obj.name for role_obj in episode.directors]:
                  meta_director      = episode.directors.new()
                  meta_director.name = sanitize_path(channel_title)
                  Log.Info(u'[ ] director: "{}"'.format(channel_title))

                for category  in Dict(json_video_details, 'categories') or []:  genre_array[category] = genre_array[category]+1 if category in genre_array else 1
                for tag       in Dict(json_video_details, 'tags')       or []:  genre_array[tag     ] = genre_array[tag     ]+1 if tag      in genre_array else 1
                
                Log.Info(u'[ ] genres:   "{}"'.format([x for x in metadata.genres]))  #metadata.genres.clear()
                for id in [id for id in genre_array if genre_array[id]>episodes/2 and id not in metadata.genres]:  metadata.genres.add(id)
                break
          
          #Loading from API
          else:
            Log(u'populate_episode_metadata_from_api() - filename: {}'.format(filename))
            result = YOUTUBE_VIDEO_REGEX.search(filename)
            if result:
              videoId = result.group('id')
              Log.Info(u'# videoId [{}] not in Playlist/channel item list so loading json_video_details'.format(videoId))
              try:                    json_video_details = json_load(YOUTUBE_json_video_details, videoId)['items'][0]
              except Exception as e:  Log('Error: "{}"'.format(e))
              else:
                Log.Info('[?] link:     "https://www.youtube.com/watch?v={}"'.format(videoId))

                # Fetch channel metadata from the video's channelId
                channel_id = Dict(json_video_details, 'snippet', 'channelId')
                if channel_id and not metadata.summary:
                  try:
                    json_channel_details = json_load(YOUTUBE_CHANNEL_DETAILS, channel_id)['items'][0]
                    Log.Info('[?] Fetched channel metadata for channelId: {}'.format(channel_id))

                    # Set channel description as show summary with URL at the top
                    if Dict(json_channel_details, 'snippet', 'description'):
                      channel_url = u'https://www.youtube.com/channel/{}'.format(channel_id)
                      channel_desc = sanitize_description(Dict(json_channel_details, 'snippet', 'description'))
                      metadata.summary = u'Channel URL: {}\n\n{}'.format(channel_url, channel_desc)
                      Log.Info('[X] Channel Description: "{}"'.format(Dict(json_channel_details, 'snippet', 'description')[:200]))

                    # Set channel images
                    thumb_channel = Dict(json_channel_details, 'snippet', 'thumbnails', 'medium', 'url') or Dict(json_channel_details, 'snippet', 'thumbnails', 'high', 'url') or Dict(json_channel_details, 'snippet', 'thumbnails', 'default', 'url')
                    if thumb_channel and thumb_channel not in metadata.posters:
                      Log.Info(u'[X] Channel Poster: {}'.format(thumb_channel))
                      metadata.posters[thumb_channel] = Proxy.Media(HTTP.Request(thumb_channel).content, sort_order=1)

                    # Set channel banner
                    banner = Dict(json_channel_details, 'brandingSettings', 'image', 'bannerExternalUrl')
                    if banner:
                      banner_url = '{}=s1920'.format(banner)
                      if banner_url not in metadata.art:
                        Log.Info(u'[X] Channel Banner: {}'.format(banner_url))
                        metadata.art[banner_url] = Proxy.Media(HTTP.Request(banner_url).content, sort_order=1)
                      if banner_url not in metadata.banners:
                        metadata.banners[banner_url] = Proxy.Media(HTTP.Request(banner_url).content, sort_order=1)

                    # Set country
                    if Dict(json_channel_details, 'snippet', 'country'):
                      metadata.countries.add(Dict(json_channel_details, 'snippet', 'country'))
                      Log.Info('[X] Channel Country: {}'.format(Dict(json_channel_details, 'snippet', 'country')))

                    # Set subscriber count as rating (formatted as millions)
                    subscriber_count = Dict(json_channel_details, 'statistics', 'subscriberCount')
                    if subscriber_count:
                      try:
                        subs = int(subscriber_count)
                        # Format as millions with 2 decimal places
                        metadata.rating = float(subs) / 1000000.0
                        # Store formatted string in content_rating for display
                        if subs >= 1000000:
                          metadata.content_rating = u'{:.2f}M'.format(subs / 1000000.0)
                        elif subs >= 1000:
                          metadata.content_rating = u'{:.1f}K'.format(subs / 1000.0)
                        else:
                          metadata.content_rating = unicode(subs)
                        Log.Info('[X] Channel Subscribers: {} (rating: {}, content_rating: {})'.format(
                          subscriber_count, metadata.rating, metadata.content_rating))
                      except:
                        pass

                    # Log all available channel metadata
                    Log.Info('[?] Channel Title: {}'.format(Dict(json_channel_details, 'snippet', 'title')))
                    Log.Info('[?] Channel Stats: {} videos, {} subscribers, {} views'.format(
                      Dict(json_channel_details, 'statistics', 'videoCount'),
                      Dict(json_channel_details, 'statistics', 'subscriberCount'),
                      Dict(json_channel_details, 'statistics', 'viewCount')
                    ))
                  except Exception as e:
                    Log('Could not fetch channel metadata: {}'.format(e))

                thumb                           = Dict(json_video_details, 'snippet', 'thumbnails', 'maxres', 'url') or Dict(json_video_details, 'snippet', 'thumbnails', 'medium', 'url') or Dict(json_video_details, 'snippet', 'thumbnails', 'standard', 'url') or Dict(json_video_details, 'snippet', 'thumbnails', 'high', 'url') or Dict(json_video_details, 'snippet', 'thumbnails', 'default', 'url')
                episode.title                   = sanitize_path(json_video_details['snippet']['title']);                                 Log.Info('[ ] title:    "{}"'.format(json_video_details['snippet']['title']))

                # Add video URL to top of episode summary and preserve newlines
                # YouTube API always returns YouTube videos
                video_url = u'https://www.youtube.com/watch?v={}'.format(videoId)
                video_desc = sanitize_description(json_video_details['snippet']['description'])
                episode.summary = u'Video URL: {}\n\n{}'.format(video_url, video_desc)
                Log.Info('[ ] summary:  "{}"'.format(json_video_details['snippet']['description'].replace('\n', '. ')))
                if len(str(e))>3:  episode.originally_available_at = Datetime.ParseDate(json_video_details['snippet']['publishedAt']).date();                       Log.Info('[ ] date:     "{}"'.format(json_video_details['snippet']['publishedAt']))
                episode.duration                = ISO8601DurationToSeconds(json_video_details['contentDetails']['duration'])*1000;               Log.Info('[ ] duration: "{}"->"{}"'.format(json_video_details['contentDetails']['duration'], episode.duration))
                if Dict(json_video_details, 'statistics', 'likeCount') and int(json_video_details['statistics']['likeCount']) > 0 and Dict(json_video_details, 'statistics', 'dislikeCount') and int(Dict(json_video_details, 'statistics', 'dislikeCount')) > 0:
                  episode.rating                = 10*float(json_video_details['statistics']['likeCount'])/(float(json_video_details['statistics']['dislikeCount'])+float(json_video_details['statistics']['likeCount']));  Log('[ ] rating:   "{}"'.format(episode.rating))
                if thumb and thumb not in episode.thumbs:
                  picture = HTTP.Request(thumb).content
                  episode.thumbs[thumb]         = Proxy.Media(picture, sort_order=1);                                                     Log.Info('[ ] thumbs:   "{}"'.format(thumb))
                  episode.thumbs.validate_keys([thumb])
                  Log.Info(u'[ ] Thumb: {}'.format(thumb))
                if Dict(json_video_details, 'snippet',  'channelTitle') and Dict(json_video_details, 'snippet',  'channelTitle') not in [role_obj.name for role_obj in episode.directors]:
                  meta_director       = episode.directors.new()
                  meta_director.name  = sanitize_path(Dict(json_video_details, 'snippet',  'channelTitle'))
                  Log.Info('[ ] director: "{}"'.format(Dict(json_video_details, 'snippet',  'channelTitle')))
                
                for id  in Dict(json_video_details, 'snippet', 'categoryId').split(',') or []:  genre_array[YOUTUBE_CATEGORY_ID[id]] = genre_array[YOUTUBE_CATEGORY_ID[id]]+1 if YOUTUBE_CATEGORY_ID[id] in genre_array else 1
                for tag in Dict(json_video_details, 'snippet', 'tags')                  or []:  genre_array[tag                    ] = genre_array[tag                    ]+1 if tag                     in genre_array else 1

              Log.Info(u'[ ] genres:   "{}"'.format([x for x in metadata.genres]))  #metadata.genres.clear()
              genre_array_cleansed = [id for id in genre_array if genre_array[id]>episodes/2 and id not in metadata.genres]  #Log.Info('[ ] genre_list: {}'.format(genre_list))
              for id in genre_array_cleansed:  metadata.genres.add(id)
            else:  Log.Info(u'videoId not found in filename')

  Log('=== End Of Agent Call, errors after that are Plex related ==='.ljust(157, '='))

### Agent declaration ##################################################################################################################################################
class YouTubeSeriesAgent(Agent.TV_Shows):
  name, primary_provider, fallback_agent, contributes_to, accepts_from, languages = 'YouTubeSeries', True, None, None, ['com.plexapp.agents.localmedia'], [Locale.Language.NoLanguage]
  def search (self, results,  media, lang, manual):  Search (results,  media, lang, manual, False)
  def update (self, metadata, media, lang, force ):  Update (metadata, media, lang, force,  False)

class YouTubeMovieAgent(Agent.Movies):
  name, primary_provider, fallback_agent, contributes_to, accepts_from, languages = 'YouTubeMovie', True, None, None, ['com.plexapp.agents.localmedia'], [Locale.Language.NoLanguage]
  def search (self, results,  media, lang, manual):  Search (results,  media, lang, manual, True)
  def update (self, metadata, media, lang, force ):  Update (metadata, media, lang, force,  True)

### Variables ###
PluginDir                = os.path.abspath(os.path.join(os.path.dirname(inspect.getfile(inspect.currentframe())), "..", ".."))
PlexRoot                 = os.path.abspath(os.path.join(PluginDir, "..", ".."))
CachePath                = os.path.join(PlexRoot, "Plug-in Support", "Data", "com.plexapp.agents.hama", "DataItems")
PLEX_LIBRARY             = {}
PLEX_LIBRARY_URL         = "http://127.0.0.1:32400/library/sections/"    # Allow to get the library name to get a log per library https://support.plex.tv/hc/en-us/articles/204059436-Finding-your-account-token-X-Plex-Token
YOUTUBE_API_BASE_URL     = "https://www.googleapis.com/youtube/v3/"
YOUTUBE_CHANNEL_ITEMS    = YOUTUBE_API_BASE_URL + 'search?order=date&part=snippet&type=video&maxResults=50&channelId={}&key={}'
YOUTUBE_CHANNEL_DETAILS  = YOUTUBE_API_BASE_URL + 'channels?part=snippet%2CcontentDetails%2Cstatistics%2CbrandingSettings&id={}&key={}'
YOUTUBE_CHANNEL_REGEX    = re.compile(r'\[(?:youtube(|2)\-)?(?P<id>UC[a-zA-Z0-9\-_]{22}|HC[a-zA-Z0-9\-_]{22})\]')
YOUTUBE_PLAYLIST_ITEMS   = YOUTUBE_API_BASE_URL + 'playlistItems?part=snippet,contentDetails&maxResults=50&playlistId={}&key={}'
YOUTUBE_PLAYLIST_DETAILS = YOUTUBE_API_BASE_URL + 'playlists?part=snippet,contentDetails&id={}&key={}'
YOUTUBE_PLAYLIST_REGEX   = re.compile(r'\[(?:youtube(|3)\-)?(?P<id>PL[^\[\]]{16}|PL[^\[\]]{32}|UU[^\[\]]{22}|FL[^\[\]]{22}|LP[^\[\]]{22}|RD[^\[\]]{22}|UC[^\[\]]{22}|HC[^\[\]]{22})\]',  re.IGNORECASE)  # https://regex101.com/r/37x8wI/2
YOUTUBE_VIDEO_SEARCH     = YOUTUBE_API_BASE_URL + 'search?&maxResults=1&part=snippet&q={}&key={}'
YOUTUBE_json_video_details    = YOUTUBE_API_BASE_URL + 'videos?part=snippet,contentDetails,statistics&id={}&key={}'
YOUTUBE_VIDEO_REGEX      = re.compile(r'(?:^\d{8}_|\[(?:youtube\-)?)(?P<id>[a-z0-9\-_]{11})(?:\]|_)', re.IGNORECASE) # https://regex101.com/r/zlHKPD/1
YOUTUBE_CATEGORY_ID      = {  '1': 'Film & Animation',  '2': 'Autos & Vehicles',  '10': 'Music',          '15': 'Pets & Animals',        '17': 'Sports',                 '18': 'Short Movies',
                             '19': 'Travel & Events',  '20': 'Gaming',            '21': 'Videoblogging',  '22': 'People & Blogs',        '23': 'Comedy',                 '24': 'Entertainment',
                             '25': 'News & Politics',  '26': 'Howto & Style',     '27': 'Education',      '28': 'Science & Technology',  '29': 'Nonprofits & Activism',  '30': 'Movies',
                             '31': 'Anime/Animation',  '32': 'Action/Adventure',  '33': 'Classics',       '34': 'Comedy',                '35': 'Documentary',            '36': 'Drama', 
                             '37': 'Family',           '38': 'Foreign',           '39': 'Horror',         '40': 'Sci-Fi/Fantasy',        '41': 'Thriller',               '42': 'Shorts',
                             '43': 'Shows',            '44': 'Trailers'}
### Plex Library XML ###
Log.Info(u"Library: "+PlexRoot)  #Log.Info(file)
token_file_path = os.path.join(PlexRoot, "X-Plex-Token.id")
if os.path.isfile(token_file_path):
  Log.Info(u"'X-Plex-Token.id' file present")
  token_file=Data.Load(token_file_path)
  if token_file:  PLEX_LIBRARY_URL += "?X-Plex-Token=" + token_file.strip()
  #Log.Info(PLEX_LIBRARY_URL) ##security risk if posting logs with token displayed
try:
  library_xml = etree.fromstring(urllib2.urlopen(PLEX_LIBRARY_URL).read())
  for library in library_xml.iterchildren('Directory'):
    for path in library.iterchildren('Location'):
      PLEX_LIBRARY[path.get("path")] = library.get("title")
      Log.Info(u"{} = {}".format(path.get("path"), library.get("title")))
except Exception as e:  Log.Info(u"Place correct Plex token in {} file or in PLEX_LIBRARY_URL variable in Code/__init__.py to have a log per library - https://support.plex.tv/hc/en-us/articles/204059436-Finding-your-account-token-X-Plex-Token, Error: {}".format(token_file_path, str(e)))
