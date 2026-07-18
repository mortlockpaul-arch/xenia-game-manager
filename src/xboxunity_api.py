import requests
import os

BASE_URL = "https://xboxunity.net/Api"
WEB_BASE_URL = "https://xboxunity.net"
RESOURCES_URL = "https://xboxunity.net/Resources/Lib"

# Reuse a single session to keep connections alive and improve performance
_session = requests.Session()

class XBoxUnity:
    def __init__(self, log_callback=None):
        self.log = log_callback

    def log_message(self, message):
        if self.log is None:
            print(message)
        elif hasattr(self.log, "emit"):
            self.log.emit(message)
        else:
            self.log(message)
    
            
    def test_connectivity(self):
        """Test basic connectivity with XboxUnity"""
        try:
            self.log_message("[INFO] Testing connectivity with XboxUnity...")
            response = _session.get("https://xboxunity.net", timeout=10)
    
            if response.status_code == 200:
                self.log_message("[INFO] Connectivity with XboxUnity: OK")
                return True
    
            self.log_message(f"[ERROR] XboxUnity responded with code: {response.status_code}")
            return False
    
        except Exception as e:
            self.log_message(f"[ERROR] Cannot connect to XboxUnity: {e}")
            return False
    
    
    def login_xboxunity(self, username, password):
        """Login using username/password and return token"""
    
        url = f"{BASE_URL}/Auth/Login"
    
        headers = {
            "User-Agent": "UnityApp/1.0",
            "Content-Type": "application/x-www-form-urlencoded"
        }
    
        payload = {
            "username": username,
            "password": password
        }
    
        try:
            self.log_message(f"[INFO] Attempting to connect to XboxUnity: {url}")
    
            response = _session.post(
                url,
                data=payload,
                headers=headers,
                timeout=30
            )
    
            self.log_message(f"[INFO] Server response: {response.status_code}")
    
            if response.status_code == 200:
                try:
                    data = response.json()
    
                    self.log_message(f"[INFO] JSON response received: {data}")
    
                    if "token" in data:
                        self.log_message("[INFO] Token obtained successfully")
                        return data["token"]
    
                    self.log_message("[ERROR] Token not found in response")
    
                except Exception as e:
                    self.log_message(f"[ERROR] Parsing login response: {e}")
                    self.log_message(f"[ERROR] Response content: {response.text[:500]}")
    
            else:
                self.log_message(f"[ERROR] HTTP status code: {response.status_code}")
                self.log_message(f"[ERROR] Server response: {response.text[:500]}")
    
        except requests.exceptions.Timeout:
            self.log_message("[ERROR] Timeout connecting to XboxUnity")
    
        except requests.exceptions.ConnectionError:
            self.log_message("[ERROR] Connection error with XboxUnity")
    
        except Exception as e:
            self.log_message(f"[ERROR] Unexpected error during login: {e}")
    
        return None
    
    
    def search_tus_real_endpoint(self, title_id, media_id=None, token=None, api_key=None):
        """
        Use the real XboxUnity endpoint discovered from web analysis.
        Filters by MediaID when supplied.
        """
    
        self.log_message(f"[INFO] Using real TitleUpdateInfo endpoint for TitleID: {title_id}")
    
        if media_id:
            self.log_message(f"[INFO] Filtering TUs only for MediaID: {media_id}")
    
        try:
            url = f"{RESOURCES_URL}/TitleUpdateInfo.php"
    
            headers = {
                "User-Agent":
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "en-US,en;q=0.5",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://xboxunity.net/"
            }
    
            params = {
                "titleid": title_id
            }
    
            self.log_message(f"[INFO] Querying: {url} with TitleID: {title_id}")
    
            response = _session.get(
                url,
                params=params,
                headers=headers,
                timeout=30
            )
    
            if response.status_code != 200:
                self.log_message(f"[ERROR] TitleUpdateInfo error: {response.status_code}")
                self.log_message(f"[ERROR] Response: {response.text[:200]}")
                return []
    
            try:
                data = response.json()
    
                self.log_message(
                    f"[INFO] TitleUpdateInfo response received: {type(data)}"
                )
    
                if not isinstance(data, dict):
                    return []
    
                found_tus = []
    
                if data.get("Type") == 1 and "MediaIDS" in data:
    
                    self.log_message("[INFO] Response type 1 - MediaIDS")
    
                    for media_item in data["MediaIDS"]:
    
                        item_media_id = media_item.get("MediaID", "")
                        updates = media_item.get("Updates", [])
    
                        if media_id and item_media_id != media_id:
                            continue
    
                        for update in updates:
    
                            file_name = (
                                f"{title_id}_"
                                f"{update.get('Version', '1')}.tu"
                            )
    
                            found_tus.append({
                                "fileName": file_name,
                                "downloadUrl":
                                    f"{RESOURCES_URL}/TitleUpdate.php?"
                                    f"tuid={update.get('TitleUpdateID', '')}",
                                "titleUpdateId":
                                    update.get("TitleUpdateID", ""),
                                "version":
                                    update.get("Version", ""),
                                "mediaId":
                                    item_media_id,
                                "titleId":
                                    title_id,
                                "titleName":
                                    update.get("Name", ""),
                                "size":
                                    update.get("Size", 0),
                                "uploadDate":
                                    update.get("UploadDate", ""),
                                "hash":
                                    update.get("hash", ""),
                                "baseVersion":
                                    update.get("BaseVersion", "")
                            })
    
                elif data.get("Type") == 2 and "Updates" in data:
    
                    self.log_message("[INFO] Response type 2 - Updates")
    
                    for update in data["Updates"]:
    
                        update_media_id = update.get("MediaID", "")
    
                        if media_id and update_media_id != media_id:
                            continue
    
                        file_name = (
                            f"{title_id}_"
                            f"{update.get('Version', '1')}.tu"
                        )
    
                        found_tus.append({
                            "fileName": file_name,
                            "downloadUrl":
                                f"{RESOURCES_URL}/TitleUpdate.php?"
                                f"tuid={update.get('TitleUpdateID', '')}",
                            "titleUpdateId":
                                update.get("TitleUpdateID", ""),
                            "version":
                                update.get("Version", ""),
                            "mediaId":
                                update_media_id,
                            "titleId":
                                title_id,
                            "titleName":
                                update.get("Name", ""),
                            "size":
                                update.get("Size", 0),
                            "uploadDate":
                                update.get("UploadDate", ""),
                            "hash":
                                update.get("hash", ""),
                            "baseVersion":
                                update.get("BaseVersion", "")
                        })
    
                self.log_message(f"[INFO] Total TUs found: {len(found_tus)}")
                return found_tus
    
            except Exception as e:
                self.log_message(f"[ERROR] Error parsing TitleUpdateInfo: {e}")
                return []
    
        except Exception as e:
            self.log_message(f"[ERROR] Error querying TitleUpdateInfo: {e}")
            return []
    
    
    def search_tus(self, media_id=None, title_id=None, token=None, api_key=None):
        """
        Main TU search function.
        """
    
        self.log_message("[INFO] Starting TU search...")
    
        if media_id:
            self.log_message(f"[INFO] MediaID: {media_id}")
    
        if title_id:
            self.log_message(f"[INFO] TitleID: {title_id}")
    
        if not title_id:
            self.log_message("[ERROR] TitleID is required")
            return []
    
        return self.search_tus_real_endpoint(
            title_id=title_id,
            media_id=media_id,
            token=token,
            api_key=api_key
        )

    @staticmethod
    def human_size(size):
        size = int(size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def download_tu(self, url, destination, progress_callback=None):
        """
        Download a TU and return:
        (success, original_filename)
        """
    
        try:
            self.log_message(f"[INFO] Downloading from: {url}")
    
            headers = {
                "User-Agent":
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/91.0.4472.124 Safari/537.36",
                "Referer": "https://xboxunity.net/"
            }
    
            directory = os.path.dirname(destination)
    
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)

            try:
                response = _session.get(
                    url,
                    headers=headers,
                    stream=True,
                    timeout=60,
                )
                response.raise_for_status()

            except requests.exceptions.HTTPError as e:
                if e.response is not None:
                    self.log_message(f"[ERROR] HTTP error: {e.response.status_code}")
                else:
                    self.log_message(f"[ERROR] HTTP error: {e}")

                return False, None

            except requests.exceptions.RequestException as e:
                self.log_message(f"[ERROR] Network error: {e}")
                return False, None
    
            original_filename = os.path.basename(destination)
    
            total_size = int(
                response.headers.get("content-length", 0)
            )
    
            downloaded = 0
    
            with open(destination, "wb") as file:
    
                for chunk in response.iter_content(chunk_size=8192):
    
                    if not chunk:
                        continue
    
                    file.write(chunk)
    
                    downloaded += len(chunk)
    
                    if progress_callback and total_size > 0:
                        progress_callback(downloaded, total_size,original_filename)
    
            self.log_message(f"[INFO] Download completed: {destination}")
    
            return True, original_filename
    
        except Exception as e:
            self.log_message(f"[ERROR] Error downloading TU: {e}")
            return False, None