"""Catalogação somente leitura dos originais, inclusive RAW via LibRaw."""
import json
from pathlib import Path
from PIL import Image, ImageOps, ExifTags
from nexus.services.files import digest, CopyItem, execute_copy
from nexus.services.manager import RAW


class Photos:
    def __init__(self, db):
        self.db = db

    def import_file(self, path: Path, tags=''):
        path = path.resolve()
        metadata = {}
        if path.suffix.lower() in RAW:
            import rawpy
            import exifread
            with path.open('rb') as stream:
                metadata = {str(k): str(v) for k, v in exifread.process_file(stream, details=False).items()
                            if 'Thumbnail' not in str(k) and 'MakerNote' not in str(k)}
            with rawpy.imread(str(path)) as raw:
                width, height = raw.sizes.width, raw.sizes.height
                try:
                    thumb = raw.extract_thumb()
                    if thumb.format == rawpy.ThumbFormat.JPEG:
                        from io import BytesIO
                        image = Image.open(BytesIO(thumb.data)).copy()
                    else:
                        image = Image.fromarray(thumb.data)
                except rawpy.LibRawNoThumbnailError:
                    image = Image.fromarray(raw.postprocess(half_size=True))
            captured = metadata.get('EXIF DateTimeOriginal', '')
            camera = metadata.get('Image Model', '')
        else:
            with Image.open(path) as original:
                width, height = original.size
                exif = original.getexif()
                metadata = {ExifTags.TAGS.get(k, str(k)): str(v) for k, v in exif.items()}
                metadata.update({ExifTags.TAGS.get(k, str(k)): str(v) for k, v in exif.get_ifd(34665).items()})
                image = ImageOps.exif_transpose(original).copy()
            captured = metadata.get('DateTimeOriginal', metadata.get('DateTime', ''))
            camera = metadata.get('Model', '')
        checksum = digest(path)
        cache = self.db.path.parent / 'thumbnails'
        cache.mkdir(exist_ok=True)
        thumb_path = cache / f'{checksum}.jpg'
        image.thumbnail((640, 640))
        image.convert('RGB').save(thumb_path, 'JPEG', quality=85)
        self.db.execute('''INSERT INTO photos(path,digest,width,height,captured,camera,tags)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET
            digest=excluded.digest,width=excluded.width,height=excluded.height,
            captured=excluded.captured,camera=excluded.camera,tags=excluded.tags''',
            (str(path), checksum, width, height, captured, camera, tags.strip()))
        photo_id = self.db.rows('SELECT id FROM photos WHERE path=?', (str(path),))[0]['id']
        self.db.execute('INSERT OR REPLACE INTO photo_details(photo_id,metadata,thumbnail) VALUES(?,?,?)',
                        (photo_id, json.dumps(metadata, ensure_ascii=False), str(thumb_path)))
        return photo_id

    def add_to_album(self, album_id, photo_id):
        self.db.execute('INSERT OR IGNORE INTO album_photos VALUES(?,?)', (album_id, photo_id))

    def backup_plan(self, album_id, destination):
        rows = self.db.rows('SELECT photos.* FROM photos JOIN album_photos ON photos.id=photo_id WHERE album_id=?', (album_id,))
        plan = []
        for row in rows:
            source = Path(row['path'])
            # IDs distinguish identical basenames from different folders.
            target = Path(destination).resolve() / f"{row['id']}_{source.name}"
            if target.exists():
                raise FileExistsError(f'O destino já existe: {target}')
            if digest(source) != row['digest']:
                raise ValueError(f'Original alterado desde a importação: {source}')
            plan.append(CopyItem(source, target, row['digest']))
        return plan
