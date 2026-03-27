import zipfile
import os

def zip_logs():
    with zipfile.ZipFile("backup.zip", "w") as z:
        for root, dirs, files in os.walk("data"):
            for file in files:
                z.write(os.path.join(root, file))
