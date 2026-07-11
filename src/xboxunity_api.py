import requests
import os

BASE_URL = "https://xboxunity.net/Api"
WEB_BASE_URL = "https://xboxunity.net"
RESOURCES_URL = "https://xboxunity.net/Resources/Lib"

# Reuse a single session to keep connections alive and improve performance
_session = requests.Session()


def test_connectivity():
    """Test basic connectivity with XboxUnity"""
    try:
        print("[INFO] Testing connectivity with XboxUnity...")
        response = _session.get("https://xboxunity.net", timeout=10)

        if response.status_code == 200:
            print("[INFO] Connectivity with XboxUnity: OK")
            return True

        print(f"[ERROR] XboxUnity responded with code: {response.status_code}")
        return False

    except Exception as e:
        print(f"[ERROR] Cannot connect to XboxUnity: {e}")
        return False


def login_xboxunity(username, password):
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
        print(f"[INFO] Attempting to connect to XboxUnity: {url}")

        response = _session.post(
            url,
            data=payload,
            headers=headers,
            timeout=30
        )

        print(f"[INFO] Server response: {response.status_code}")

        if response.status_code == 200:
            try:
                data = response.json()

                print(f"[INFO] JSON response received: {data}")

                if "token" in data:
                    print("[INFO] Token obtained successfully")
                    return data["token"]

                print("[ERROR] Token not found in response")

            except Exception as e:
                print(f"[ERROR] Parsing login response: {e}")
                print(f"[ERROR] Response content: {response.text[:500]}")

        else:
            print(f"[ERROR] HTTP status code: {response.status_code}")
            print(f"[ERROR] Server response: {response.text[:500]}")

    except requests.exceptions.Timeout:
        print("[ERROR] Timeout connecting to XboxUnity")

    except requests.exceptions.ConnectionError:
        print("[ERROR] Connection error with XboxUnity")

    except Exception as e:
        print(f"[ERROR] Unexpected error during login: {e}")

    return None


def search_tus_real_endpoint(title_id, media_id=None, token=None, api_key=None):
    """
    Use the real XboxUnity endpoint discovered from web analysis.
    Filters by MediaID when supplied.
    """

    print(f"[INFO] Using real TitleUpdateInfo endpoint for TitleID: {title_id}")

    if media_id:
        print(f"[INFO] Filtering TUs only for MediaID: {media_id}")

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

        print(f"[INFO] Querying: {url} with TitleID: {title_id}")

        response = _session.get(
            url,
            params=params,
            headers=headers,
            timeout=30
        )

        if response.status_code != 200:
            print(f"[ERROR] TitleUpdateInfo error: {response.status_code}")
            print(f"[ERROR] Response: {response.text[:200]}")
            return []

        try:
            data = response.json()

            print(
                f"[INFO] TitleUpdateInfo response received: {type(data)}"
            )

            if not isinstance(data, dict):
                return []

            found_tus = []

            if data.get("Type") == 1 and "MediaIDS" in data:

                print("[INFO] Response type 1 - MediaIDS")

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

                print("[INFO] Response type 2 - Updates")

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

            print(f"[INFO] Total TUs found: {len(found_tus)}")
            return found_tus

        except Exception as e:
            print(f"[ERROR] Error parsing TitleUpdateInfo: {e}")
            return []

    except Exception as e:
        print(f"[ERROR] Error querying TitleUpdateInfo: {e}")
        return []


def search_tus(media_id=None, title_id=None, token=None, api_key=None):
    """
    Main TU search function.
    """

    print("[INFO] Starting TU search...")

    if media_id:
        print(f"[INFO] MediaID: {media_id}")

    if title_id:
        print(f"[INFO] TitleID: {title_id}")

    if not title_id:
        print("[ERROR] TitleID is required")
        return []

    return search_tus_real_endpoint(
        title_id=title_id,
        media_id=media_id,
        token=token,
        api_key=api_key
    )


def download_tu(url, destination, progress_callback=None):
    """
    Download a TU and return:
    (success, original_filename)
    """

    try:
        print(f"[INFO] Downloading from: {url}")

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

        response = _session.get(
            url,
            headers=headers,
            stream=True,
            timeout=60
        )

        if response.status_code != 200:
            print(f"[ERROR] Download error: {response.status_code}")
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

        print(f"[INFO] Download completed: {destination}")

        return True, original_filename

    except Exception as e:
        print(f"[ERROR] Error downloading TU: {e}")
        return False, None