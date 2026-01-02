#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Consolidated YouTube Agent Test Runner

This script:
1. Validates Plex compatibility
2. Imports and runs the actual agent code
3. Recursively processes .info.json files in a directory
4. Queries YouTube API using the agent's logic
5. Outputs detailed results for each file

Usage:
    python test_agent_run.py <data_dir> [--api-key YOUR_KEY] [--verbose]

Example:
    python test_agent_run.py ./data
    python test_agent_run.py ./data --api-key AIza... --verbose
"""

from __future__ import print_function
import sys
import os
import json
import argparse
import re
from io import open  # Python 2/3 compatible file opening with encoding support

# Python 2/3 compatibility
try:
    import __builtin__  # Python 2
except ImportError:
    import builtins as __builtin__  # Python 3

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def safe_unicode_print(text):
    """Safely print text that may contain Unicode, encoding to UTF-8 in Python 2."""
    if sys.version_info[0] < 3 and isinstance(text, unicode):
        return text.encode('utf-8')
    return text

def print_colored(text, color):
    """Print colored text to terminal."""
    # Handle Unicode in Python 2
    if sys.version_info[0] < 3:
        try:
            if isinstance(text, unicode):
                text = text.encode('utf-8')
        except NameError:
            pass  # Python 3, no unicode type
    print("{}{}{}".format(color, text, Colors.ENDC))

def print_header(text):
    """Print a header."""
    print_colored("\n" + "=" * 80, Colors.HEADER)
    print_colored(text, Colors.HEADER + Colors.BOLD)
    print_colored("=" * 80, Colors.HEADER)

def print_success(text):
    """Print success message."""
    if sys.version_info[0] < 3 and isinstance(text, unicode):
        text = text.encode('utf-8')
    print_colored("✓ " + text, Colors.OKGREEN)

def print_error(text):
    """Print error message."""
    if sys.version_info[0] < 3 and isinstance(text, unicode):
        text = text.encode('utf-8')
    print_colored("✗ " + text, Colors.FAIL)

def print_warning(text):
    """Print warning message."""
    if sys.version_info[0] < 3 and isinstance(text, unicode):
        text = text.encode('utf-8')
    print_colored("⚠ " + text, Colors.WARNING)

def print_info(text):
    """Print info message."""
    if sys.version_info[0] < 3 and isinstance(text, unicode):
        text = text.encode('utf-8')
    print_colored("ℹ " + text, Colors.OKBLUE)


# ============================================================================
# PHASE 1: Plex Compatibility Validation
# ============================================================================

def validate_plex_compatibility(agent_file):
    """Validate that the agent code is Plex-compatible."""
    print_header("PHASE 1: Plex Compatibility Validation")

    if not os.path.exists(agent_file):
        print_error("Agent file not found: {}".format(agent_file))
        return False

    with open(agent_file, 'r', encoding='utf-8') as f:
        code = f.read()

    issues = []
    warnings = []

    # Check for Python 3 imports (should use Python 2)
    if 'from urllib import request' in code or 'import urllib.request' in code:
        issues.append("Python 3 urllib imports found (Plex uses Python 2.7)")

    # Check for correct Python 2 imports
    if 'import urllib2' in code and 'import urllib' in code:
        print_success("Python 2.7 urllib imports: OK")

    # Check for deprecated Regex() usage
    if re.search(r'Regex\s*\(', code):
        issues.append("Deprecated Regex() found (use re.compile() instead)")

    # Check for re.compile() usage
    if 'YOUTUBE_CHANNEL_REGEX = re.compile' in code:
        print_success("Regex patterns use re.compile(): OK")

    # Check for UTF-8 encoding in open()
    utf8_count = len(re.findall(r"open\([^)]+encoding=['\"]utf-8['\"]", code))
    if utf8_count > 0:
        print_success("UTF-8 encoding in open() calls: {} found".format(utf8_count))
    else:
        warnings.append("No UTF-8 encoding found in open() calls (may cause mojibake)")

    # Check for sanitize_xml_string function
    if 'def sanitize_xml_string' in code:
        print_success("sanitize_xml_string() function: Found")
    else:
        warnings.append("sanitize_xml_string() not found (may have XML issues)")

    # Check for list() wrapper in iteration
    if 'for c in list(s):' in code:
        print_success("RestrictedPython sandbox workaround: Found")
    else:
        warnings.append("RestrictedPython sandbox workaround not found")

    # Report issues
    if issues:
        print_error("\nCOMPATIBILITY ISSUES FOUND ({}):".format(len(issues)))
        for issue in issues:
            print("  - " + issue)
        return False

    if warnings:
        print_warning("\nWARNINGS ({}):".format(len(warnings)))
        for warning in warnings:
            print("  - " + warning)

    if not issues:
        print_success("\nPlex compatibility: PASS")

    return True


# ============================================================================
# PHASE 2: Mock Plex Framework Setup
# ============================================================================

class MockLog:
    """Mock Plex Log object."""
    def __call__(self, message):
        # Allow Log() to be called directly
        # Encode Unicode to UTF-8 for Python 2 compatibility
        if sys.version_info[0] < 3 and isinstance(message, unicode):
            message = message.encode('utf-8')
        print("[LOG] {}".format(message))

    @staticmethod
    def Info(message):
        # Encode Unicode to UTF-8 for Python 2 compatibility
        if sys.version_info[0] < 3 and isinstance(message, unicode):
            message = message.encode('utf-8')
        print("[LOG] {}".format(message))

    @staticmethod
    def Debug(message):
        pass  # Suppress debug logs

    @staticmethod
    def Warn(message):
        # Encode Unicode to UTF-8 for Python 2 compatibility
        if sys.version_info[0] < 3 and isinstance(message, unicode):
            message = message.encode('utf-8')
        print("[WARN] {}".format(message))

    @staticmethod
    def Error(message):
        # Encode Unicode to UTF-8 for Python 2 compatibility
        if sys.version_info[0] < 3 and isinstance(message, unicode):
            message = message.encode('utf-8')
        print("[ERROR] {}".format(message))

class MockHTTP:
    """Mock Plex HTTP object."""
    Headers = {}
    CacheTime = 0

    @staticmethod
    def Request(url, **kwargs):
        """Make real HTTP request for testing with manual redirect and cookie handling."""
        import urllib2
        try:
            import http.cookiejar as cookielib  # Python 3
        except ImportError:
            import cookielib  # Python 2

        class Response:
            def __init__(self, content):
                self.content = content

        try:
            # Get headers from kwargs or use defaults
            headers = kwargs.get('headers', {})

            # Add default headers if not specified
            if 'User-Agent' not in headers:
                headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'

            # Special handling for VK channel URLs - manually extract and set cookies
            if 'vkvideo.ru/@public' in url:
                print("[HTTP] VK channel URL detected, using manual cookie handling")

                # Step 1: Request channel URL WITHOUT auto-redirect
                class NoRedirectHandler(urllib2.HTTPRedirectHandler):
                    def http_error_302(self, req, fp, code, msg, headers):
                        return fp  # Don't follow redirect, return response
                    http_error_301 = http_error_303 = http_error_307 = http_error_302

                opener = urllib2.build_opener(NoRedirectHandler())
                req = urllib2.Request(url)
                for key, value in headers.items():
                    req.add_header(key, value)

                try:
                    response = opener.open(req, timeout=10)

                    # Read response headers
                    print("[HTTP] Step 1 - Initial request status: {}".format(response.code))
                    redirect_location = response.headers.get('Location')

                    # Extract Set-Cookie headers
                    cookies = {}
                    for header_name, header_value in response.headers.items():
                        if header_name.lower() == 'set-cookie':
                            print("[HTTP] Set-Cookie found: {}".format(header_value[:80]))
                            # Parse cookie name=value
                            cookie_parts = header_value.split(';')[0].split('=', 1)
                            if len(cookie_parts) == 2:
                                cookies[cookie_parts[0]] = cookie_parts[1]

                    if redirect_location:
                        print("[HTTP] Step 2 - Following redirect: {}".format(redirect_location[:80]))

                        # Follow redirect to get anonymous token
                        req2 = urllib2.Request(redirect_location)
                        for key, value in headers.items():
                            req2.add_header(key, value)

                        response2 = opener.open(req2, timeout=10)
                        print("[HTTP] Step 2 - Redirect response status: {}".format(response2.code))

                        # Extract more cookies from redirect response
                        for header_name, header_value in response2.headers.items():
                            if header_name.lower() == 'set-cookie':
                                print("[HTTP] Set-Cookie from redirect: {}".format(header_value[:80]))
                                cookie_parts = header_value.split(';')[0].split('=', 1)
                                if len(cookie_parts) == 2:
                                    cookies[cookie_parts[0]] = cookie_parts[1]

                        if cookies:
                            print("[HTTP] ✓ Cookies collected: {}".format(len(cookies)))
                            for name, value in cookies.items():
                                print("[HTTP]   - {}: {}...".format(name, value[:20]))

                            # Step 3: Retry original URL with cookies
                            print("[HTTP] Step 3 - Retrying original URL with cookies...")
                            cookie_header = '; '.join(['{}={}'.format(k, v) for k, v in cookies.items()])

                            # Use normal opener for final request
                            req3 = urllib2.Request(url)
                            for key, value in headers.items():
                                req3.add_header(key, value)
                            req3.add_header('Cookie', cookie_header)

                            normal_opener = urllib2.build_opener()
                            response3 = normal_opener.open(req3, timeout=10)
                            content = response3.read()
                            print("[HTTP] ✓ Successfully fetched channel page (status: {})".format(response3.code))
                            return Response(content)

                    # No redirect, return original response
                    content = response.read()
                    return Response(content)

                except Exception as e:
                    print("[HTTP] Failed in manual cookie flow: {}".format(e))
                    return Response(b'')

            # Standard request for non-VK URLs
            cookie_jar = cookielib.CookieJar()
            opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookie_jar))

            req = urllib2.Request(url)
            for key, value in headers.items():
                req.add_header(key, value)

            response = opener.open(req, timeout=10)
            content = response.read()
            return Response(content)

        except Exception as e:
            print("[HTTP] Failed to fetch {}: {}".format(url, e))
            return Response(b'')

class MockJSON:
    """Mock Plex JSON object."""
    @staticmethod
    def ObjectFromString(json_str):
        return json.loads(json_str)

    @staticmethod
    def StringFromObject(obj):
        return json.dumps(obj)

    @staticmethod
    def ObjectFromURL(url, cacheTime=None):
        """Fetch JSON from URL (makes real HTTP request)."""
        try:
            # Python 2/3 compatible URL fetching
            try:
                import urllib2
                response = urllib2.urlopen(url)
                data = response.read()
            except ImportError:
                import urllib.request
                response = urllib.request.urlopen(url)
                data = response.read()

            # Decode bytes to string if needed (Python 3)
            if isinstance(data, bytes):
                data = data.decode('utf-8')

            return json.loads(data)
        except Exception as e:
            # Create an exception with .content attribute like Plex does
            error_obj = type('HTTPError', (Exception,), {
                'content': json.dumps({'error': {'code': 'HTTP_ERROR', 'message': str(e)}})
            })()
            raise error_obj

class MockDatetime:
    """Mock Plex Datetime object."""
    @staticmethod
    def ParseDate(date_str):
        if not date_str:
            return None
        # Simple mock - just return a year
        class MockDate:
            year = int(date_str[:4]) if date_str and len(date_str) >= 4 else None
            def date(self):
                return self
        return MockDate()

class MockDict:
    """Mock Plex Dict object."""
    pass

class MockProxy:
    """Mock Plex Proxy object."""
    class Media:
        @staticmethod
        def __init__(content, sort_order=None):
            pass

class MockString:
    """Mock Plex String object."""
    @staticmethod
    def Quote(s, usePlus=False):
        try:
            from urllib import quote
            return quote(s, safe='')
        except ImportError:
            from urllib.parse import quote
            return quote(s, safe='')

class MockCore:
    """Mock Plex Core object."""
    class storage:
        @staticmethod
        def load(path):
            with open(path, 'r') as f:
                return f.read()

class MockData:
    """Mock Plex Data object."""
    @staticmethod
    def Load(path):
        """Load data from a file (mimics Plex Data.Load())."""
        try:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    return f.read()
        except:
            pass
        return None

class MockMetadataSearchResult:
    """Mock Plex MetadataSearchResult."""
    def __init__(self, id, name, year=None, score=100, lang='en'):
        self.id = id
        self.name = name
        self.year = year
        self.score = score
        self.lang = lang

    def __repr__(self):
        return "MetadataSearchResult(id='{}', name='{}', year={}, score={})".format(
            self.id, self.name, self.year, self.score)

class MockResults:
    """Mock search results container."""
    def __init__(self):
        self.results = []

    def Append(self, result):
        self.results.append(result)

    def __len__(self):
        return len(self.results)

    def __iter__(self):
        return iter(self.results)

class Python2CompatDict(dict):
    """Dict subclass that mimics Python 2 dict.keys() behavior (returns list)."""
    def keys(self):
        return list(super(Python2CompatDict, self).keys())

    def values(self):
        return list(super(Python2CompatDict, self).values())

    def items(self):
        return list(super(Python2CompatDict, self).items())

class PlexProxyContainer(Python2CompatDict):
    """Dict subclass that mimics Plex ProxyContainer (for thumbs, posters, art, etc)."""
    def validate_keys(self, keys):
        """Plex validation method - we just ignore it in tests."""
        pass

class MockRole:
    """Mock Plex Role object."""
    def __init__(self):
        self.role = ''
        self.name = ''
        self.photo = ''

class MockDirector:
    """Mock Plex Director object."""
    def __init__(self):
        self.name = ''

class PlexObjectContainer(list):
    """List subclass that mimics Plex object containers (for roles, directors, etc)."""
    def __init__(self, factory):
        super(PlexObjectContainer, self).__init__()
        self.factory = factory

    def new(self):
        """Create a new object and add it to the container."""
        obj = self.factory()
        self.append(obj)
        return obj

class MockMedia:
    """Mock Plex Media object."""
    def __init__(self, filename, show_name, file_path=None):
        self.filename = filename
        self.show = show_name
        self.name = show_name
        self.seasons = Python2CompatDict()
        # For GetMediaDir() to work properly
        if file_path:
            class MockPart:
                def __init__(self, file_path):
                    self.file = file_path
            class MockItem:
                def __init__(self, file_path):
                    self.parts = [MockPart(file_path)]
            class MockEpisode:
                def __init__(self, file_path):
                    self.items = [MockItem(file_path)]
            class MockSeason:
                def __init__(self, file_path):
                    self.episodes = {1: MockEpisode(file_path)}
            # Set up TV show structure
            self.seasons = Python2CompatDict({2025: MockSeason(file_path)})
            # Also set items for movie structure
            self.items = [MockItem(file_path)]

class MockEpisodeMetadata:
    """Mock Plex Episode metadata."""
    def __init__(self):
        self.title = ''
        self.summary = ''
        self.originally_available_at = None
        self.duration = None
        self.thumbs = PlexProxyContainer()
        self.directors = PlexObjectContainer(MockDirector)
        self.roles = PlexObjectContainer(MockRole)
        self.guest_stars = []
        self.writers = []
        self.producers = []

class AutoCreateDict(Python2CompatDict):
    """Dict that auto-creates missing keys with a factory function."""
    def __init__(self, factory, *args, **kwargs):
        super(AutoCreateDict, self).__init__(*args, **kwargs)
        self._factory = factory

    def __getitem__(self, key):
        if key not in self:
            self[key] = self._factory()
        return super(AutoCreateDict, self).__getitem__(key)

class MockSeasonMetadata:
    """Mock Plex Season metadata."""
    def __init__(self):
        self.episodes = AutoCreateDict(MockEpisodeMetadata)

class MockMetadata:
    """Mock Plex Metadata object."""
    def __init__(self, guid):
        self.id = guid
        self.title = ''
        self.summary = ''
        self.originally_available_at = None
        self.rating = None
        self.content_rating = ''
        self.seasons = AutoCreateDict(MockSeasonMetadata)
        self.posters = PlexProxyContainer()
        self.art = PlexProxyContainer()
        self.banners = PlexProxyContainer()
        self.themes = PlexProxyContainer()
        self.directors = PlexObjectContainer(MockDirector)
        self.roles = PlexObjectContainer(MockRole)
        self.genres = set()
        self.countries = set()

def setup_mocks(api_key=None):
    """Setup all Plex Framework mocks."""
    print_header("PHASE 2: Setting Up Mock Plex Framework")

    # Python 2/3 compatibility
    try:
        import __builtin__ as builtins
    except ImportError:
        import builtins

    # Mock lxml with proper etree attribute
    class MockLxmlEtree:
        @staticmethod
        def fromstring(s):
            return None
        @staticmethod
        def tostring(element):
            return ''

    class MockLxml:
        etree = MockLxmlEtree()

    sys.modules['lxml'] = MockLxml()
    sys.modules['lxml.etree'] = MockLxmlEtree()

    # Mock Python 2 modules for Python 3 compatibility
    if sys.version_info[0] >= 3:
        import urllib.request
        import urllib.parse
        import urllib.error
        sys.modules['urllib2'] = urllib.request
        sys.modules['urllib'] = urllib.parse
        # Mock unicode type (Python 2 only)
        builtins.unicode = str

    # Set Plex Framework built-ins
    builtins.CACHE_1MONTH = 2592000
    builtins.CACHE_1WEEK = 604800
    builtins.CACHE_1DAY = 86400
    builtins.CACHE_1HOUR = 3600

    builtins.Log = MockLog()
    builtins.HTTP = MockHTTP()
    builtins.JSON = MockJSON()
    builtins.Datetime = MockDatetime()
    builtins.Dict = MockDict()
    builtins.Proxy = MockProxy()
    builtins.String = MockString()
    builtins.Core = MockCore()
    builtins.Data = MockData()
    builtins.MetadataSearchResult = MockMetadataSearchResult

    # Mock Agent class for Plex plugin
    class MockAgent:
        class TV_Shows:
            pass
        class Movies:
            pass
    builtins.Agent = MockAgent()

    # Mock Locale class
    class MockLocale:
        class Language:
            NoLanguage = 'xx'
    builtins.Locale = MockLocale()

    # Set YouTube API key if provided
    if api_key:
        builtins.YOUTUBE_API_KEY = api_key
        print_success("YouTube API key: Set")
    else:
        builtins.YOUTUBE_API_KEY = ''
        print_warning("YouTube API key: Not set (API calls will fail)")

    print_success("Mock framework: Ready")


# ============================================================================
# PHASE 3: Import and Run Agent
# ============================================================================

def import_agent(agent_dir):
    """Import the agent code."""
    print_header("PHASE 3: Importing Agent Code")

    # Add agent directory to Python path
    if agent_dir not in sys.path:
        sys.path.insert(0, agent_dir)

    try:
        # Import the agent module
        import __init__ as agent
        print_success("Agent imported successfully")

        # Verify key functions exist
        if hasattr(agent, 'Search'):
            print_success("Search() function: Found")
        else:
            print_error("Search() function: NOT FOUND")
            return None

        if hasattr(agent, 'Update'):
            print_success("Update() function: Found")
        else:
            print_error("Update() function: NOT FOUND")
            return None

        return agent

    except Exception as e:
        print_error("Failed to import agent: {}".format(e))
        import traceback
        traceback.print_exc()
        return None


# ============================================================================
# PHASE 4: Process Files and Query YouTube API
# ============================================================================

def find_info_json_files(data_dir):
    """Recursively find all .info.json files."""
    info_files = []
    for root, dirs, files in os.walk(data_dir):
        for filename in files:
            if filename.endswith('.info.json'):
                info_files.append(os.path.join(root, filename))
    return sorted(info_files)

def find_video_files(data_dir):
    """Recursively find all video files (.mp4, .mkv, etc.)."""
    video_files = []
    video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.MP4', '.MKV')
    for root, dirs, files in os.walk(data_dir):
        for filename in files:
            if filename.endswith(video_extensions):
                # Check if corresponding .info.json exists
                base_name = os.path.splitext(filename)[0]
                info_json = os.path.join(root, base_name + '.info.json')
                if not os.path.exists(info_json):
                    # No .info.json - will use YouTube API
                    video_files.append(os.path.join(root, filename))
    return sorted(video_files)

def process_file(agent, info_file, verbose=False):
    """Process a single .info.json file."""
    print_header("Processing: {}".format(os.path.basename(info_file)))

    # Read the .info.json file
    try:
        with open(info_file, 'r', encoding='utf-8') as f:
            video_data = json.load(f)
    except Exception as e:
        print_error("Failed to read file: {}".format(e))
        return False

    # Extract video information
    video_id = video_data.get('id', 'UNKNOWN')
    title = video_data.get('title', 'UNKNOWN')
    uploader = video_data.get('uploader', 'UNKNOWN')
    upload_date = video_data.get('upload_date', 'UNKNOWN')

    # Encode Unicode strings for Python 2 compatibility
    if sys.version_info[0] < 3:
        if isinstance(video_id, unicode):
            video_id = video_id.encode('utf-8')
        if isinstance(title, unicode):
            title = title.encode('utf-8')
        if isinstance(uploader, unicode):
            uploader = uploader.encode('utf-8')
        if isinstance(upload_date, unicode):
            upload_date = upload_date.encode('utf-8')

    print_info("File: {}".format(os.path.basename(info_file)))
    print_info("Video ID: {}".format(video_id))
    print_info("Title: {}".format(title))
    print_info("Uploader: {}".format(uploader))
    print_info("Upload Date: {}".format(upload_date))

    # Prepare mock media and results objects
    mp4_file = info_file.replace('.info.json', '.mp4')
    mp4_filename = os.path.basename(mp4_file)

    show_name = os.path.basename(os.path.dirname(os.path.dirname(info_file)))

    # Pass full path for GetMediaDir() to work (even if .mp4 doesn't exist)
    media = MockMedia(mp4_filename, show_name, file_path=mp4_file)
    results = MockResults()

    # Run Search() function
    print("\n--- Running Search() ---")
    try:
        agent.Search(results, media, 'en', False, False)

        if len(results) > 0:
            print_success("Search found {} result(s)".format(len(results)))
            for i, result in enumerate(results):
                print("  [{}] ID: {}".format(i+1, safe_unicode_print(result.id)))
                print("      Name: {}".format(safe_unicode_print(result.name)))
                print("      Year: {}".format(result.year))
                print("      Score: {}".format(result.score))
        else:
            print_warning("Search returned no results")

        # If we have a result, run Update()
        if len(results) > 0:
            print("\n--- Running Update() ---")
            metadata = MockMetadata(results.results[0].id)

            try:
                agent.Update(metadata, media, 'en', True, False)

                print_success("Update completed")
                print("\n--- Metadata That Would Be Sent to Plex ---")

                # Show-level metadata
                print("\n[SHOW METADATA]")
                print("  Title: {}".format(metadata.title if metadata.title else "(empty)"))
                if hasattr(metadata, 'summary') and metadata.summary:
                    summary_preview = metadata.summary[:200] + "..." if len(metadata.summary) > 200 else metadata.summary
                    print("  Summary: {}".format(summary_preview))
                    print("  Summary Length: {} characters".format(len(metadata.summary)))
                else:
                    print("  Summary: (empty)")

                if hasattr(metadata, 'originally_available_at') and metadata.originally_available_at:
                    print("  Date: {}".format(metadata.originally_available_at))

                if hasattr(metadata, 'countries') and metadata.countries:
                    print("  Countries: {}".format(", ".join(metadata.countries)))

                if hasattr(metadata, 'rating') and metadata.rating:
                    print("  Rating: {:.2f}".format(metadata.rating))

                if hasattr(metadata, 'content_rating') and metadata.content_rating:
                    print("  Content Rating (Subscribers): {}".format(metadata.content_rating))

                # Images
                if hasattr(metadata, 'posters') and metadata.posters:
                    print("\n[POSTERS] ({} image(s))".format(len(metadata.posters)))
                    for i, url in enumerate(list(metadata.posters.keys())[:3], 1):
                        print("  {}. {}".format(i, url[:80] + "..." if len(url) > 80 else url))
                    if len(metadata.posters) > 3:
                        print("  ... and {} more".format(len(metadata.posters) - 3))

                if hasattr(metadata, 'art') and metadata.art:
                    print("\n[BACKGROUND ART] ({} image(s))".format(len(metadata.art)))
                    for i, url in enumerate(list(metadata.art.keys())[:3], 1):
                        print("  {}. {}".format(i, url[:80] + "..." if len(url) > 80 else url))

                if hasattr(metadata, 'banners') and metadata.banners:
                    print("\n[BANNERS] ({} image(s))".format(len(metadata.banners)))
                    for i, url in enumerate(list(metadata.banners.keys())[:3], 1):
                        print("  {}. {}".format(i, url[:80] + "..." if len(url) > 80 else url))

                # Roles/Cast
                if hasattr(metadata, 'roles') and metadata.roles:
                    print("\n[ROLES/CAST] ({} role(s))".format(len(metadata.roles)))
                    for role in metadata.roles[:5]:
                        if hasattr(role, 'name'):
                            print("  - {}{}".format(role.name, " ({})".format(role.role) if hasattr(role, 'role') else ""))

                # Genres
                if hasattr(metadata, 'genres') and metadata.genres:
                    print("\n[GENRES] {}".format(", ".join(metadata.genres)))

                # Episode-level metadata
                if hasattr(metadata, 'seasons') and len(metadata.seasons) > 0:
                    print("\n[EPISODES]")
                    for season_num in sorted(metadata.seasons.keys()):
                        season = metadata.seasons[season_num]
                        if hasattr(season, 'episodes') and len(season.episodes) > 0:
                            print("  Season {}:".format(season_num))
                            for ep_num in sorted(list(season.episodes.keys())[:3]):
                                episode = season.episodes[ep_num]
                                ep_title = episode.title if hasattr(episode, 'title') and episode.title else "(no title)"
                                print("    Episode {}: {}".format(ep_num, ep_title))

                                # Show episode details
                                if hasattr(episode, 'summary') and episode.summary:
                                    summary_preview = episode.summary[:300] + "..." if len(episode.summary) > 300 else episode.summary
                                    print("      Summary: {}".format(summary_preview))
                                if hasattr(episode, 'duration') and episode.duration:
                                    duration_mins = episode.duration / 60000
                                    print("      Duration: {:.1f} minutes".format(duration_mins))
                                if hasattr(episode, 'originally_available_at') and episode.originally_available_at:
                                    print("      Air Date: {}".format(episode.originally_available_at))
                                if hasattr(episode, 'thumbs') and episode.thumbs and len(episode.thumbs) > 0:
                                    print("      Thumbnail: {}".format(list(episode.thumbs.keys())[0][:60] + "..."))
                                if hasattr(episode, 'directors') and episode.directors:
                                    directors = ", ".join([d.name for d in episode.directors if hasattr(d, 'name')])
                                    if directors:
                                        print("      Director: {}".format(directors))
                            if len(season.episodes) > 3:
                                print("    ... and {} more episode(s)".format(len(season.episodes) - 3))

            except Exception as e:
                print_error("Update() failed: {}".format(e))
                import traceback
                traceback.print_exc()  # Always print traceback for debugging

        return True

    except Exception as e:
        print_error("Search() failed: {}".format(e))
        import traceback
        traceback.print_exc()  # Always print traceback for debugging
        return False


def process_video_file(agent, video_file, verbose=False):
    """Process a video file without .info.json (uses YouTube API)."""
    print_header("Processing: {} (YouTube API)".format(os.path.basename(video_file)))

    try:
        # Extract video info from filename
        filename = os.path.basename(video_file)
        dirname = os.path.dirname(video_file)

        # Extract show name from directory structure
        dir_parts = dirname.split(os.sep)
        show_name = dir_parts[-2] if 'Season' in dir_parts[-1] else dir_parts[-1]

        print_info("File: {}".format(filename))
        print_info("Directory: {}".format(dirname))
        print_info("Show: {}".format(show_name))

        # Create mock media object
        media = MockMedia(filename, show_name, file_path=video_file)

        # Run Search()
        print("\n--- Running Search() ---")
        results = MockResults()

        try:
            agent.Search(results, media, 'en', False, False)

            if len(results) > 0:
                print_success("Search found {} result(s)".format(len(results)))
                for i, result in enumerate(results.results, 1):
                    print("  Result {}:".format(i))
                    print("      ID: {}".format(result.id))
                    print("      Name: {}".format(result.name))
            else:
                print_warning("Search returned no results")

        except Exception as e:
            print_error("Search() failed: {}".format(e))
            import traceback
            traceback.print_exc()  # Always print traceback for debugging
            return False

        # If we have a result, run Update()
        if len(results) > 0:
            print("\n--- Running Update() (will use YouTube API) ---")
            metadata = MockMetadata(results.results[0].id)

            try:
                agent.Update(metadata, media, 'en', True, False)

                print_success("Update completed")
                print("\n--- Metadata That Would Be Sent to Plex ---")

                # Show-level metadata
                print("\n[SHOW METADATA]")
                print("  Title: {}".format(metadata.title if metadata.title else "(empty)"))
                if hasattr(metadata, 'summary') and metadata.summary:
                    summary_preview = metadata.summary[:200] + "..." if len(metadata.summary) > 200 else metadata.summary
                    print("  Summary: {}".format(summary_preview))
                    print("  Summary Length: {} characters".format(len(metadata.summary)))
                else:
                    print("  Summary: (empty)")

                if hasattr(metadata, 'originally_available_at') and metadata.originally_available_at:
                    print("  Date: {}".format(metadata.originally_available_at))

                if hasattr(metadata, 'countries') and metadata.countries:
                    print("  Countries: {}".format(", ".join(metadata.countries)))

                if hasattr(metadata, 'rating') and metadata.rating:
                    print("  Rating: {:.2f}".format(metadata.rating))

                if hasattr(metadata, 'content_rating') and metadata.content_rating:
                    print("  Content Rating (Subscribers): {}".format(metadata.content_rating))

                # Images
                if hasattr(metadata, 'posters') and metadata.posters:
                    print("\n[POSTERS] ({} image(s))".format(len(metadata.posters)))
                    for i, url in enumerate(list(metadata.posters.keys())[:3], 1):
                        print("  {}. {}".format(i, url[:80] + "..." if len(url) > 80 else url))
                    if len(metadata.posters) > 3:
                        print("  ... and {} more".format(len(metadata.posters) - 3))

                if hasattr(metadata, 'art') and metadata.art:
                    print("\n[BACKGROUND ART] ({} image(s))".format(len(metadata.art)))
                    for i, url in enumerate(list(metadata.art.keys())[:3], 1):
                        print("  {}. {}".format(i, url[:80] + "..." if len(url) > 80 else url))

                if hasattr(metadata, 'banners') and metadata.banners:
                    print("\n[BANNERS] ({} image(s))".format(len(metadata.banners)))
                    for i, url in enumerate(list(metadata.banners.keys())[:3], 1):
                        print("  {}. {}".format(i, url[:80] + "..." if len(url) > 80 else url))

                # Roles/Cast
                if hasattr(metadata, 'roles') and metadata.roles:
                    print("\n[ROLES/CAST] ({} role(s))".format(len(metadata.roles)))
                    for role in metadata.roles[:5]:
                        if hasattr(role, 'name'):
                            print("  - {}{}".format(role.name, " ({})".format(role.role) if hasattr(role, 'role') else ""))

                # Genres
                if hasattr(metadata, 'genres') and metadata.genres:
                    print("\n[GENRES] {}".format(", ".join(metadata.genres)))

                # Episode-level metadata
                if hasattr(metadata, 'seasons') and len(metadata.seasons) > 0:
                    print("\n[EPISODES]")
                    for season_num in sorted(metadata.seasons.keys()):
                        season = metadata.seasons[season_num]
                        if hasattr(season, 'episodes') and len(season.episodes) > 0:
                            print("  Season {}:".format(season_num))
                            for ep_num in sorted(list(season.episodes.keys())[:3]):
                                episode = season.episodes[ep_num]
                                ep_title = episode.title if hasattr(episode, 'title') and episode.title else "(no title)"
                                print("    Episode {}: {}".format(ep_num, ep_title))

                                # Show episode details
                                if hasattr(episode, 'summary') and episode.summary:
                                    summary_preview = episode.summary[:300] + "..." if len(episode.summary) > 300 else episode.summary
                                    print("      Summary: {}".format(summary_preview))
                                if hasattr(episode, 'duration') and episode.duration:
                                    duration_mins = episode.duration / 60000
                                    print("      Duration: {:.1f} minutes".format(duration_mins))
                                if hasattr(episode, 'originally_available_at') and episode.originally_available_at:
                                    print("      Air Date: {}".format(episode.originally_available_at))
                                if hasattr(episode, 'thumbs') and episode.thumbs and len(episode.thumbs) > 0:
                                    print("      Thumbnail: {}".format(list(episode.thumbs.keys())[0][:60] + "..."))
                                if hasattr(episode, 'directors') and episode.directors:
                                    directors = ", ".join([d.name for d in episode.directors if hasattr(d, 'name')])
                                    if directors:
                                        print("      Director: {}".format(directors))
                            if len(season.episodes) > 3:
                                print("    ... and {} more episode(s)".format(len(season.episodes) - 3))

                return True

            except Exception as e:
                print_error("Update() failed: {}".format(e))
                import traceback
                traceback.print_exc()  # Always print traceback for debugging
                return False

        return False

    except Exception as e:
        print_error("Failed to process video file: {}".format(e))
        if verbose:
            import traceback
            traceback.print_exc()
        return False


# ============================================================================
# PHASE 5: Unit Tests for Actor/Role Extraction
# ============================================================================

import tempfile
import shutil

class ActorRoleTestResult:
    """Store test results for actor/role extraction tests."""
    def __init__(self, test_name, passed, message='', details=None):
        self.test_name = test_name
        self.passed = passed
        self.message = message
        self.details = details or {}

def create_test_info_json(test_dir, filename, info_data):
    """Create a test .info.json file with the given data.

    Args:
        test_dir: Directory to create the file in
        filename: Base filename (without extension)
        info_data: Dictionary with info.json contents

    Returns:
        Path to the created .info.json file
    """
    json_path = os.path.join(test_dir, filename + '.info.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(info_data, f, ensure_ascii=False, indent=2)
    return json_path

def run_actor_extraction_test(agent, test_name, info_data, expected_name, expected_role):
    """Run a single actor extraction test.

    Args:
        agent: The imported agent module
        test_name: Name of the test case
        info_data: Dictionary with info.json contents
        expected_name: Expected actor name (or None if no actor expected)
        expected_role: Expected role title (or None if no actor expected)

    Returns:
        ActorRoleTestResult with test outcome
    """
    # Create temporary test directory structure
    # Structure: temp_dir/Show Name/Season 2025/video.info.json
    temp_dir = tempfile.mkdtemp(prefix='yt_agent_test_')

    try:
        show_dir = os.path.join(temp_dir, 'Test Show')
        season_dir = os.path.join(show_dir, 'Season 2025')
        os.makedirs(season_dir)

        # Create test .info.json file
        video_filename = 'test_video_{}'.format(info_data.get('id', 'test123'))
        json_path = create_test_info_json(season_dir, video_filename, info_data)

        # Create mock media object
        mp4_path = json_path.replace('.info.json', '.mp4')
        media = MockMedia(os.path.basename(mp4_path), 'Test Show', file_path=mp4_path)

        # Run Search to get ID
        results = MockResults()
        try:
            agent.Search(results, media, 'en', False, False)
        except Exception as e:
            return ActorRoleTestResult(
                test_name, False,
                'Search() failed: {}'.format(e)
            )

        if len(results) == 0:
            return ActorRoleTestResult(
                test_name, False,
                'Search() returned no results'
            )

        # Run Update to populate metadata
        metadata = MockMetadata(results.results[0].id)
        try:
            agent.Update(metadata, media, 'en', True, False)
        except Exception as e:
            return ActorRoleTestResult(
                test_name, False,
                'Update() failed: {}'.format(e)
            )

        # Check actor/role extraction
        if expected_name is None:
            # Expect no roles
            if len(metadata.roles) == 0:
                return ActorRoleTestResult(
                    test_name, True,
                    'Correctly created no roles',
                    {'roles_count': 0}
                )
            else:
                return ActorRoleTestResult(
                    test_name, False,
                    'Expected no roles but found {}'.format(len(metadata.roles)),
                    {'roles_count': len(metadata.roles)}
                )
        else:
            # Expect specific actor/role
            if len(metadata.roles) == 0:
                return ActorRoleTestResult(
                    test_name, False,
                    'Expected actor "{}" but no roles were created'.format(expected_name),
                    {'roles_count': 0}
                )

            # Check first role
            role = metadata.roles[0]
            actual_name = role.name if hasattr(role, 'name') else None
            actual_role = role.role if hasattr(role, 'role') else None

            if actual_name == expected_name and actual_role == expected_role:
                return ActorRoleTestResult(
                    test_name, True,
                    'Actor "{}" with role "{}" correctly extracted'.format(actual_name, actual_role),
                    {'name': actual_name, 'role': actual_role}
                )
            else:
                return ActorRoleTestResult(
                    test_name, False,
                    'Expected name="{}", role="{}" but got name="{}", role="{}"'.format(
                        expected_name, expected_role, actual_name, actual_role
                    ),
                    {'expected_name': expected_name, 'expected_role': expected_role,
                     'actual_name': actual_name, 'actual_role': actual_role}
                )

    finally:
        # Clean up temp directory
        try:
            shutil.rmtree(temp_dir)
        except:
            pass

def run_actor_role_unit_tests(agent):
    """Run all actor/role extraction unit tests.

    Args:
        agent: The imported agent module

    Returns:
        Tuple of (passed_count, failed_count, results_list)
    """
    print_header("UNIT TESTS: Actor/Role Extraction")

    test_cases = [
        # Test 1: Basic creator field
        {
            'name': 'Basic creator field',
            'info': {
                'id': 'test_creator_001',
                'title': 'Test Video with Creator',
                'description': 'Test description',
                'creator': 'Jane Doe',
                'upload_date': '20240101',
                'duration': 300
            },
            'expected_name': 'Jane Doe',
            'expected_role': 'Instructor'
        },
        # Test 2: Uploader fallback (no creator)
        {
            'name': 'Uploader fallback (no creator)',
            'info': {
                'id': 'test_uploader_002',
                'title': 'Test Video with Uploader Only',
                'description': 'Test description',
                'uploader': 'John Smith',
                'upload_date': '20240101',
                'duration': 300
            },
            'expected_name': 'John Smith',
            'expected_role': 'Instructor'
        },
        # Test 3: Creator takes priority over uploader
        {
            'name': 'Creator takes priority over uploader',
            'info': {
                'id': 'test_priority_003',
                'title': 'Test Video with Both Fields',
                'description': 'Test description',
                'creator': 'Creator Name',
                'uploader': 'Uploader Name',
                'upload_date': '20240101',
                'duration': 300
            },
            'expected_name': 'Creator Name',
            'expected_role': 'Instructor'
        },
        # Test 4: Channel fallback (no creator or uploader)
        {
            'name': 'Channel fallback (no creator or uploader)',
            'info': {
                'id': 'test_channel_004',
                'title': 'Test Video with Channel Only',
                'description': 'Test description',
                'channel': 'Channel Name',
                'upload_date': '20240101',
                'duration': 300
            },
            'expected_name': 'Channel Name',
            'expected_role': 'Instructor'
        },
        # Test 5: Education category -> Instructor role
        {
            'name': 'Education category sets Instructor role',
            'info': {
                'id': 'test_education_005',
                'title': 'Educational Video',
                'description': 'Test description',
                'uploader': 'Professor Smith',
                'categories': ['Education', 'Tutorial'],
                'upload_date': '20240101',
                'duration': 300
            },
            'expected_name': 'Professor Smith',
            'expected_role': 'Instructor'
        },
        # Test 6: Podcast category -> Host role
        {
            'name': 'Podcast category sets Host role',
            'info': {
                'id': 'test_podcast_006',
                'title': 'Podcast Episode',
                'description': 'Test description',
                'uploader': 'Podcast Host',
                'categories': ['Podcast'],
                'upload_date': '20240101',
                'duration': 300
            },
            'expected_name': 'Podcast Host',
            'expected_role': 'Host'
        },
        # Test 7: Music category -> Artist role
        {
            'name': 'Music category sets Artist role',
            'info': {
                'id': 'test_music_007',
                'title': 'Music Video',
                'description': 'Test description',
                'uploader': 'Band Name',
                'categories': ['Music'],
                'upload_date': '20240101',
                'duration': 300
            },
            'expected_name': 'Band Name',
            'expected_role': 'Artist'
        },
        # Test 8: No actor fields -> no roles created
        {
            'name': 'No actor fields creates no roles',
            'info': {
                'id': 'test_noactor_008',
                'title': 'Video Without Actor Info',
                'description': 'Test description',
                'upload_date': '20240101',
                'duration': 300
            },
            'expected_name': None,
            'expected_role': None
        },
        # Test 9: Unicode actor name
        {
            'name': 'Unicode actor name handling',
            'info': {
                'id': 'test_unicode_009',
                'title': 'Video with Unicode Creator',
                'description': 'Test description',
                'creator': u'Müller François 日本語',
                'upload_date': '20240101',
                'duration': 300
            },
            'expected_name': u'Müller François 日本語',
            'expected_role': 'Instructor'
        },
        # Test 10: Vlog category -> Creator role
        {
            'name': 'Vlog category sets Creator role',
            'info': {
                'id': 'test_vlog_010',
                'title': 'My Vlog',
                'description': 'Test description',
                'uploader': 'Vlogger',
                'tags': ['vlog', 'personal'],
                'upload_date': '20240101',
                'duration': 300
            },
            'expected_name': 'Vlogger',
            'expected_role': 'Creator'
        },
    ]

    results = []
    passed = 0
    failed = 0

    for test_case in test_cases:
        print("\n--- Test: {} ---".format(test_case['name']))
        result = run_actor_extraction_test(
            agent,
            test_case['name'],
            test_case['info'],
            test_case['expected_name'],
            test_case['expected_role']
        )
        results.append(result)

        if result.passed:
            print_success(result.message)
            passed += 1
        else:
            print_error(result.message)
            failed += 1

    # Print summary
    print("\n" + "-" * 40)
    print("Actor/Role Unit Tests: {} passed, {} failed".format(passed, failed))

    return passed, failed, results


# ============================================================================
# Main Test Runner
# ============================================================================

def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(
        description='YouTube Agent Test Runner - Test agent with real data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s ./data
  %(prog)s ./data --api-key YOUR_API_KEY
  %(prog)s ./data --api-key YOUR_API_KEY --verbose

API Key:
  Place your YouTube API key in youtube-key.txt (one line, no quotes)
  Or use --api-key parameter (command line overrides file)
        """
    )

    parser.add_argument('data_dir', nargs='?', default=None, help='Directory containing test data (.info.json files)')
    parser.add_argument('--api-key', help='YouTube API key for real API queries (overrides youtube-key.txt)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output with full tracebacks')
    parser.add_argument('--unit-tests', '-u', action='store_true', help='Run unit tests for actor/role extraction')

    args = parser.parse_args()

    # Validate inputs - data_dir required unless running unit tests only
    if not args.unit_tests and (args.data_dir is None or not os.path.isdir(args.data_dir)):
        if args.data_dir is None:
            print_error("data_dir required unless using --unit-tests")
        else:
            print_error("Data directory not found: {}".format(args.data_dir))
        return 1

    # Get paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    agent_dir = os.path.join(os.path.dirname(script_dir), 'Code')
    agent_file = os.path.join(agent_dir, '__init__.py')

    print_colored("\n" + "=" * 80, Colors.BOLD)
    print_colored("YouTube Agent Test Runner", Colors.BOLD)
    print_colored("=" * 80, Colors.BOLD)
    print()
    print("Agent: {}".format(agent_file))
    if args.data_dir:
        print("Data:  {}".format(os.path.abspath(args.data_dir)))
    if args.unit_tests:
        print("Mode:  Unit Tests ")
    print()

    # Phase 1: Validate Plex compatibility
    if not validate_plex_compatibility(agent_file):
        print_error("\nPlex compatibility validation FAILED!")
        print_error("Fix compatibility issues before testing")
        return 1

    # Load API key from file if not provided via command line
    api_key = args.api_key
    if not api_key:
        api_key_file = os.path.join(script_dir, 'youtube-key.txt')
        if os.path.exists(api_key_file):
            try:
                with open(api_key_file, 'r') as f:
                    api_key = f.read().strip()
                    if api_key:
                        print_info("Loaded YouTube API key from: {}".format(api_key_file))
            except Exception as e:
                print_warning("Failed to read API key from {}: {}".format(api_key_file, e))

    # Phase 2: Setup mocks
    setup_mocks(api_key=api_key)

    # Phase 3: Import agent
    agent = import_agent(agent_dir)
    if not agent:
        print_error("\nFailed to import agent!")
        return 1

    # Run unit tests if requested
    if args.unit_tests:
        unit_passed, unit_failed, unit_results = run_actor_role_unit_tests(agent)

        # If only unit tests requested (no data_dir), exit here
        if args.data_dir is None:
            print()
            if unit_failed > 0:
                print_error("Unit tests completed with {} failure(s)".format(unit_failed))
                return 1
            else:
                print_success("All {} unit tests passed!".format(unit_passed))
                return 0

    # Phase 4: Find and process files
    print_header("PHASE 4: Processing Test Files")

    info_files = find_info_json_files(args.data_dir)
    video_files = find_video_files(args.data_dir)

    total_files = len(info_files) + len(video_files)

    if total_files == 0:
        print_warning("No test files found in {}".format(args.data_dir))
        return 0

    if info_files:
        print_info("Found {} .info.json file(s)".format(len(info_files)))
    if video_files:
        print_info("Found {} video file(s) without .info.json (will use YouTube API)".format(len(video_files)))
    print()

    # Process each file
    success_count = 0
    failure_count = 0

    # Process .info.json files first
    for info_file in info_files:
        if process_file(agent, info_file, verbose=args.verbose):
            success_count += 1
        else:
            failure_count += 1
        print()  # Blank line between files

    # Process video files without .info.json (will use YouTube API)
    for video_file in video_files:
        if process_video_file(agent, video_file, verbose=args.verbose):
            success_count += 1
        else:
            failure_count += 1
        print()  # Blank line between files

    # Final summary
    print_header("SUMMARY")
    print("Total files processed: {}".format(total_files))
    print_success("Successful: {}".format(success_count))
    if failure_count > 0:
        print_error("Failed: {}".format(failure_count))
    else:
        print_success("Failed: 0")

    print()

    return 0 if failure_count == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
