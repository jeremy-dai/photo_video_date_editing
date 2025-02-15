from datetime import datetime
from mutagen.mp4 import MP4
from PIL import Image
import os
import piexif
import shutil
import subprocess
import time
from pillow_heif import register_heif_opener
import re
from moviepy import VideoFileClip
from pathlib import Path


image_extensions = {'.jpg', '.jpeg', '.tiff', '.tif'}
video_extensions = {'.mp4', '.MP4', '.m4v'}


def move_invalid_files(input_folder):
    root_folder = os.path.dirname(input_folder)
    invalid_folder = os.path.join(root_folder, "invalid_files")
    os.makedirs(invalid_folder, exist_ok=True)

    for filename in os.listdir(input_folder):
        if os.path.splitext(filename.lower())[1] not in image_extensions:
            if os.path.splitext(filename.lower())[1] not in video_extensions:
                print(f"******** Moving {filename} (Unknown file type)")
                shutil.move(os.path.join(input_folder, filename),
                            os.path.join(invalid_folder, filename))
            continue


def move_short_videos(source_folder, destination_folder, max_duration=4):
    """
    Find videos shorter than specified duration and move them to a new folder.

    Args:
        source_folder (str): Path to the folder containing videos
        destination_folder (str): Path to the folder where short videos will be moved
        max_duration (float): Maximum duration in seconds (default: 4)
    """
    # Create destination folder if it doesn't exist
    Path(destination_folder).mkdir(parents=True, exist_ok=True)

    # Get all video files
    video_files = []
    for ext in ['.mov', '.mp4', '.MP4', '.MOV']:
        video_files.extend(Path(source_folder).glob(f'*{ext}'))

    moved_count = 0

    for video_path in video_files:
        try:
            # Load video and get duration
            with VideoFileClip(str(video_path)) as video:
                duration = video.duration

            # If video is shorter than max_duration, move it
            if duration < max_duration:
                destination_path = Path(destination_folder) / video_path.name
                video_path.rename(destination_path)
                print(f"Moved {video_path.name} (Duration: {duration:.2f}s)")
                moved_count += 1

        except Exception as e:
            print(f"Error processing {video_path.name}: {str(e)}")

    print(f"\nMoved {moved_count} videos shorter than {max_duration} seconds")


def modify_image_dates(input_folder, new_date_str, output_folder=None, name_addition=""):
    """
    Batch modify EXIF dates for all images in a folder.
    """

    # Validate the date format
    try:
        new_date = datetime.strptime(new_date_str, '%Y:%m:%d %H:%M:%S')
    except ValueError:
        print("Error: Date must be in format 'YYYY:MM:DD HH:MM:SS'")
        return

    # Setup output folder
    if output_folder is None:
        output_folder = os.path.join(input_folder, "modified_images")

    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    # Convert date to bytes for EXIF
    date_str = new_date.strftime('%Y:%m:%d %H:%M:%S')
    date_bytes = date_str.encode('utf-8')

    # Process all files in the folder
    image_extensions = {'.jpg', '.jpeg', '.tiff', '.tif'}
    successful = 0
    failed = 0

    for filename in os.listdir(input_folder):
        if os.path.splitext(filename.lower())[1] not in image_extensions:
            continue

        input_path = os.path.join(input_folder, filename)
        output_path = os.path.join(output_folder, name_addition + filename)

        try:
            # Load EXIF data
            exif_dict = piexif.load(input_path)

            # Update all date fields in EXIF
            if "0th" in exif_dict:
                exif_dict["0th"][piexif.ImageIFD.DateTime] = date_bytes
            if "Exif" in exif_dict:
                exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = date_bytes
                exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = date_bytes

            # Convert modified EXIF data to bytes
            exif_bytes = piexif.dump(exif_dict)

            # Copy image and update EXIF
            shutil.copy2(input_path, output_path)
            piexif.insert(exif_bytes, output_path)

            successful += 1

        except Exception as e:
            failed += 1
            print(f"Failed to process {filename}: {str(e)}")

    if successful > 0:
        print(f"\nProcessing complete:")
        print(f"Successfully processed: {successful} images")
        print(f"Modified images saved to: {output_folder}")
    if failed > 0:
        print(
            f"!!!!!!!!!!!!!!! Failed to process: {failed} images !!!!!!!!!!!!!!!")


def modify_video_dates(input_folder, new_date_str, output_folder=None, name_addition=""):
    """
    Batch modify creation dates for MP4 videos in a folder, with special handling for GoPro files.
    """

    # First, check if ffmpeg is available
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True)
    except FileNotFoundError:
        print("Error: ffmpeg is not installed. Please install ffmpeg first.")
        return

    # Validate the date format
    try:
        new_date = datetime.strptime(new_date_str, '%Y:%m:%d %H:%M:%S')
        # Convert to Unix timestamp
        timestamp = time.mktime(new_date.timetuple())
        # Format date for ffmpeg
        ffmpeg_date = new_date.strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        print("Error: Date must be in format 'YYYY:MM:DD HH:MM:SS'")
        return

    # Setup output folder
    if output_folder is None:
        output_folder = os.path.join(input_folder, "modified_videos")

    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    # Process all files in the folder
    video_extensions = {'.mp4', '.MP4', '.m4v'}
    successful = 0
    failed = 0

    for filename in os.listdir(input_folder):
        if os.path.splitext(filename)[1] not in video_extensions:
            continue

        input_path = os.path.join(input_folder, filename)
        output_path = os.path.join(output_folder, name_addition + filename)
        temp_path = output_path + '.temp.mp4'

        try:
            # Use ffmpeg to modify metadata
            cmd = [
                'ffmpeg', '-i', input_path,
                '-metadata', f'creation_time={ffmpeg_date}',
                '-c', 'copy',  # Copy without re-encoding
                '-map_metadata', '0',  # Copy all other metadata
                temp_path
            ]

            # Run ffmpeg
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                raise Exception(f"FFmpeg error: {result.stderr}")

            # Move temp file to final destination
            if os.path.exists(output_path):
                os.remove(output_path)
            os.rename(temp_path, output_path)

            # Update file system timestamps
            os.utime(output_path, (timestamp, timestamp))

            # Try to update additional metadata with mutagen
            try:
                video = MP4(output_path)
                video["©day"] = str(new_date.year)
                video["©tim"] = new_date.strftime('%H:%M:%S')
                video["creation_time"] = [
                    new_date.strftime('%Y-%m-%dT%H:%M:%SZ')]
                video.save()
            except Exception as e:
                print(
                    f"Warning: Could not update additional metadata for {filename}: {str(e)}")

            successful += 1

        except Exception as e:
            failed += 1
            print(f"Failed to process {filename}: {str(e)}")
            # Clean up failed files
            for path in [temp_path, output_path]:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except:
                        pass
    if successful > 0:
        print("\nProcessing complete:")
        print(f"Successfully processed: {successful} videos")
        print(f"Modified videos saved to: {output_folder}")
    if failed > 0:
        print(
            f"!!!!!!!!!!!!!!! Failed to process: {failed} videos !!!!!!!!!!!!!!!")


def filter_images_by_year(input_folder, target_year, keep_folder=None, move_folder=None):
    """
    Filter images based on their EXIF date. Keep files from target year, move others.

    Args:
        input_folder (str): Path to folder containing images
        target_year (int): Target year to filter by
        keep_folder (str, optional): Path to folder for keeping matched files
        move_folder (str, optional): Path to folder for moving unmatched files
    """

    # Setup output folders
    root_folder = os.path.dirname(input_folder)
    if keep_folder is None:
        keep_folder = os.path.join(root_folder, f"year_{target_year}")
    if move_folder is None:
        move_folder = os.path.join(root_folder, "other_years")

    # Create output folders if they don't exist
    os.makedirs(keep_folder, exist_ok=True)
    os.makedirs(move_folder, exist_ok=True)

    # Process all files in the folder

    kept = 0
    moved = 0
    failed = 0

    for filename in os.listdir(input_folder):
        if os.path.splitext(filename.lower())[1] not in image_extensions:
            continue

        input_path = os.path.join(input_folder, filename)

        try:
            # Load EXIF data
            exif_dict = piexif.load(input_path)

            # Try to get original date from EXIF
            date_str = None
            if "Exif" in exif_dict and piexif.ExifIFD.DateTimeOriginal in exif_dict["Exif"]:
                date_str = exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal].decode(
                    'utf-8')
            elif "0th" in exif_dict and piexif.ImageIFD.DateTime in exif_dict["0th"]:
                date_str = exif_dict["0th"][piexif.ImageIFD.DateTime].decode(
                    'utf-8')

            if date_str:
                file_year = datetime.strptime(
                    date_str, '%Y:%m:%d %H:%M:%S').year

                # Determine destination based on year
                if file_year == target_year:
                    dest_folder = keep_folder
                    kept += 1
                else:
                    print(f"Moved {filename} (Year: {file_year})")
                    dest_folder = move_folder
                    moved += 1

                # Copy file to appropriate folder
                shutil.copy2(input_path, os.path.join(dest_folder, filename))

            else:
                # If no date found, move to other years folder
                shutil.copy2(input_path, os.path.join(move_folder, filename))
                moved += 1
                print(f"No date found in {filename}, moved to other years")

        except Exception as e:
            failed += 1
            print(f"Failed to process {filename}: {str(e)}")

    print(f"\nProcessing complete:")
    print(f"Files from {target_year}: {kept}")
    print(f"Files from other years: {moved}")
    print(f"Failed to process: {failed}")
    print(f"Matching files saved to: {keep_folder}")
    print(f"Other files saved to: {move_folder}")


def filter_videos_by_year(input_folder, target_year, keep_folder=None, move_folder=None):
    """
    Filter videos based on their creation date. Keep files from target year, move others.
    """

    # Setup output folders
    root_folder = os.path.dirname(input_folder)
    if keep_folder is None:
        keep_folder = os.path.join(root_folder, f"year_{target_year}")
    if move_folder is None:
        move_folder = os.path.join(root_folder, "other_years")

    # Create output folders if they don't exist
    os.makedirs(keep_folder, exist_ok=True)
    os.makedirs(move_folder, exist_ok=True)

    # Process all files in the folder
    kept = 0
    moved = 0
    failed = 0

    for filename in os.listdir(input_folder):
        if os.path.splitext(filename)[1] not in video_extensions:
            continue

        input_path = os.path.join(input_folder, filename)

        try:
            # Try to get date from MP4 metadata
            video = MP4(input_path)
            file_year = None

            # Check various metadata fields for date
            if 'creation_time' in video:
                date_str = video['creation_time'][0]
                file_year = datetime.strptime(
                    date_str, '%Y-%m-%dT%H:%M:%SZ').year
            elif '©day' in video:
                file_year = int(video['©day'][0])

            # If no date in metadata, try file modification time
            if file_year is None:
                file_year = datetime.fromtimestamp(
                    os.path.getmtime(input_path)).year
                print(
                    f"No metadata date found for {filename}, using file modification date")

            # Determine destination based on year
            if file_year == target_year:
                dest_folder = keep_folder
                kept += 1
            else:
                dest_folder = move_folder
                moved += 1

            # Copy file to appropriate folder
            shutil.copy2(input_path, os.path.join(dest_folder, filename))
            print(f"Processed {filename} (Year: {file_year})")

        except Exception as e:
            failed += 1
            print(f"Failed to process {filename}: {str(e)}")

    print(f"\nProcessing complete:")
    print(f"Files from {target_year}: {kept}")
    print(f"Files from other years: {moved}")
    print(f"Failed to process: {failed}")
    print(f"Matching files saved to: {keep_folder}")
    print(f"Other files saved to: {move_folder}")


def get_heic_creation_date(image_path):
    """Extract creation date from HEIC file's EXIF data."""
    try:
        with Image.open(image_path) as img:
            exif_dict = piexif.load(img.info.get('exif', b''))
            if exif_dict.get('Exif') and piexif.ExifIFD.DateTimeOriginal in exif_dict['Exif']:
                date_str = exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal].decode(
                    'utf-8')
                return datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
    except Exception as e:
        print(f"Warning: Could not extract creation date: {e}")
    return None


def convert_heic_to_jpg(input_path, output_path=None):
    """Convert HEIC file to JPG while preserving creation date."""
    # Register HEIF opener
    register_heif_opener()

    # If output path is not specified, create one
    if output_path is None:
        output_path = os.path.splitext(input_path)[0] + '.jpg'

    try:
        # Get creation date before conversion
        creation_date = get_heic_creation_date(input_path)

        # Open and convert image
        with Image.open(input_path) as img:
            # Preserve EXIF data if available
            exif_dict = piexif.load(img.info.get('exif', b''))

            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')

            # Save as JPG with original EXIF data
            if exif_dict:
                exif_bytes = piexif.dump(exif_dict)
                img.save(output_path, 'JPEG', quality=100, exif=exif_bytes)
            else:
                img.save(output_path, 'JPEG', quality=100)

        # If we found a creation date, update the file's modification time
        if creation_date:
            timestamp = creation_date.timestamp()
            os.utime(output_path, (timestamp, timestamp))

        return True

    except Exception as e:
        print(f"Error converting {input_path}: {e}")
        return False


def batch_convert_heic_to_jpg(input_folder, output_folder=None):
    """Convert all HEIC files in a folder to JPG."""
    if output_folder is None:
        output_folder = input_folder

    if not os.path.exists(output_folder):
        os.makedirs(output_folder, exist_ok=True)

    success_count = 0
    fail_count = 0

    for filename in os.listdir(input_folder):
        if filename.lower().endswith('.heic'):
            input_path = os.path.join(input_folder, filename)
            output_path = os.path.join(output_folder,
                                       os.path.splitext(filename)[0] + '.jpg')

            if convert_heic_to_jpg(input_path, output_path):
                success_count += 1
            else:
                fail_count += 1

    print(f"\nConversion complete!")
    print(f"Successfully converted: {success_count} files")
    print(f"Failed conversions: {fail_count} files")


def get_png_creation_date(image_path):
    """Extract creation date from PNG file's EXIF data."""
    try:
        with Image.open(image_path) as img:
            if 'exif' in img.info:
                exif_dict = piexif.load(img.info['exif'])
                if exif_dict.get('Exif') and piexif.ExifIFD.DateTimeOriginal in exif_dict['Exif']:
                    date_str = exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal].decode(
                        'utf-8')
                    return datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
    except Exception as e:
        print(f"Warning: Could not extract creation date: {e}")
    return None


def convert_png_to_jpg(input_path, output_path=None):
    """Convert PNG file to JPG while preserving creation date."""
    # If output path is not specified, create one
    if output_path is None:
        output_path = os.path.splitext(input_path)[0] + '.jpg'

    try:
        # Get creation date before conversion
        creation_date = get_png_creation_date(input_path)

        # Open and convert image
        with Image.open(input_path) as img:
            # Get EXIF data if available
            exif_dict = None
            if 'exif' in img.info:
                exif_dict = piexif.load(img.info['exif'])

            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'LA', 'P'):
                # Create white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'RGBA':
                    # Use alpha channel as mask
                    background.paste(img, mask=img.split()[3])
                else:
                    background.paste(img)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Save as JPG with original EXIF data if available
            if exif_dict:
                exif_bytes = piexif.dump(exif_dict)
                img.save(output_path, 'JPEG', quality=95, exif=exif_bytes)
            else:
                img.save(output_path, 'JPEG', quality=95)

        # If we found a creation date, update the file's modification time
        if creation_date:
            timestamp = creation_date.timestamp()
            os.utime(output_path, (timestamp, timestamp))

        return True

    except Exception as e:
        print(f"Error converting {input_path}: {e}")
        return False


def batch_convert_png_to_jpg(input_folder, output_folder=None):
    """Convert all PNG files in a folder to JPG."""
    if output_folder is None:
        output_folder = input_folder

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    success_count = 0
    fail_count = 0

    for filename in os.listdir(input_folder):
        if filename.lower().endswith('.png'):
            input_path = os.path.join(input_folder, filename)
            output_path = os.path.join(output_folder,
                                       os.path.splitext(filename)[0] + '.jpg')

            if convert_png_to_jpg(input_path, output_path):
                success_count += 1
            else:
                fail_count += 1

    print(f"\nConversion complete!")
    print(f"Successfully converted: {success_count} files")
    print(f"Failed conversions: {fail_count} files")


def move_files_by_name(input_folder, output_folder):
    root_folder = os.path.dirname(input_folder)
    unknown_folder = os.path.join(root_folder, "unknown")

    # Create unknown folder
    os.makedirs(unknown_folder, exist_ok=True)

    # Dictionary to track statistics
    stats = {
        'matched': 0,
        'unknown': 0,
        'failed': 0
    }

   # Regular expressions for date patterns with validation
    patterns = [
        # yyyy-mm-dd: Matches 1900-2099, months 01-12, days 01-31
        r'(?P<year>19\d{2}|20\d{2})-(?P<month>0[1-9]|1[0-2])-(?P<day>0[1-9]|[12]\d|3[01])',

        # yyyymmdd: Matches 1900-2099, months 01-12, days 01-31
        r'(?P<year>19\d{2}|20\d{2})(?P<month>0[1-9]|1[0-2])(?P<day>0[1-9]|[12]\d|3[01])',

        # Also match with dots: yyyy.mm.dd
        r'(?P<year>19\d{2}|20\d{2})\.(?P<month>0[1-9]|1[0-2])\.(?P<day>0[1-9]|[12]\d|3[01])',

        # Also match with underscores: yyyy_mm_dd
        r'(?P<year>19\d{2}|20\d{2})_(?P<month>0[1-9]|1[0-2])_(?P<day>0[1-9]|[12]\d|3[01])'
    ]

    for filename in os.listdir(input_folder):
        input_path = os.path.join(input_folder, filename)

        # Skip if it's a directory
        if os.path.isdir(input_path):
            continue

        try:
            date_found = False

            # Check each pattern
            for pattern in patterns:
                match = re.search(pattern, filename)
                if match:
                    # Extract month and day
                    year, month, day = match.groups()

                    # Create mmdd folder
                    mmdd_folder = os.path.join(output_folder, f"{month}{day}")
                    os.makedirs(mmdd_folder, exist_ok=True)

                    # Move file to appropriate folder
                    dest_path = os.path.join(mmdd_folder, filename)
                    shutil.move(input_path, dest_path)

                    stats['matched'] += 1
                    date_found = True
                    break

            # If no date pattern found, move to unknown folder
            if not date_found:
                shutil.move(input_path, os.path.join(unknown_folder, filename))
                stats['unknown'] += 1

        except Exception as e:
            stats['failed'] += 1
            print(f"Failed to process {filename}: {str(e)}")

    # Print summary
    print("\nProcessing complete:")
    print(f"Files matched and sorted: {stats['matched']}")
    print(f"Files without date pattern: {stats['unknown']}")
    print(f"Failed to process: {stats['failed']}")
