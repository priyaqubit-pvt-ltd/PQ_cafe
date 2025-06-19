from flask import Flask, request, jsonify, send_file, render_template, send_from_directory
from flask_cors import CORS
from PIL import Image, ImageOps
import io
import os
import uuid
import atexit
from werkzeug.utils import secure_filename
from rembg import remove
from flask import session
import base64

app = Flask(__name__)
CORS(app)

app.secret_key = 'your-secret-key-here-change-this-in-production'

# Configuration
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def cleanup_files():
    """Clean up old files in upload folder"""
    try:
        for filename in os.listdir(UPLOAD_FOLDER):
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
    except Exception as e:
        print(f"Error during cleanup: {e}")

def get_proper_format(ext):
    """Get proper PIL format for saving"""
    ext_lower = ext.lower()
    formats = {'jpg': 'JPEG', 'jpeg': 'JPEG', 'png': 'PNG', 'gif': 'GIF', 'bmp': 'BMP', 'webp': 'WEBP'}
    return formats.get(ext_lower, 'JPEG')

def get_proper_mimetype(ext):
    """Get proper mimetype for the file"""
    ext_lower = ext.lower()
    mimetypes = {
        'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
        'gif': 'image/gif', 'bmp': 'image/bmp', 'webp': 'image/webp'
    }
    return mimetypes.get(ext_lower, 'image/jpeg')

# Clean up files when app starts and register cleanup on shutdown
cleanup_files()
atexit.register(cleanup_files)

# Add these routes to your app.py file

# Add these routes to your app.py file

@app.route('/cropupload')
def crop_upload_page():
    """Serve the crop upload page"""
    cleanup_files()
    try:
        return render_template('cropupload.html')
    except:
        return jsonify({'message': 'Crop Upload page - cropupload.html template not found'}), 404

@app.route('/crop')
def crop_tool_page():
    """Serve the crop tool page"""
    try:
        return render_template('crop.html')
    except:
        return jsonify({'message': 'Crop page - crop.html template not found'}), 404

@app.route('/upload_image_for_crop', methods=['POST'])
def upload_image_for_crop():
    """Handle image upload for crop tool"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        if not file.filename or not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Invalid file type. Supported formats: PNG, JPG, JPEG, GIF, BMP, WEBP'}), 400
        
        # Validate file size (10MB limit)
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)  # Reset file pointer
        
        max_size = 10 * 1024 * 1024  # 10MB
        if file_size > max_size:
            return jsonify({'success': False, 'error': 'File size must be less than 10MB'}), 400
        
        # Save uploaded file
        original_filename = secure_filename(file.filename)
        ext = original_filename.rsplit('.', 1)[1].lower()
        unique_id = str(uuid.uuid4())
        saved_filename = f"crop_{unique_id}.{ext}"
        filepath = os.path.join(UPLOAD_FOLDER, saved_filename)
        file.save(filepath)
        
        # Get image dimensions
        with Image.open(filepath) as img:
            width, height = img.size
        
        return jsonify({
            'success': True,
            'filename': saved_filename,
            'original_filename': original_filename,
            'image_url': f'/image/{saved_filename}',
            'dimensions': {'width': width, 'height': height}
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error uploading image: {str(e)}'}), 500

@app.route('/process_crop', methods=['POST'])
def process_crop():
    """Process the crop operation with coordinates from frontend"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        # Get crop parameters
        filename = data.get('filename')
        crop_x = int(data.get('x', 0))
        crop_y = int(data.get('y', 0))
        crop_width = int(data.get('width', 0))
        crop_height = int(data.get('height', 0))
        
        if not filename:
            return jsonify({'success': False, 'error': 'No filename provided'}), 400
        
        if crop_width <= 0 or crop_height <= 0:
            return jsonify({'success': False, 'error': 'Invalid crop dimensions'}), 400
        
        # Validate file exists
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if not os.path.exists(filepath):
            return jsonify({'success': False, 'error': 'Image file not found'}), 404
        
        # Open and crop image
        with Image.open(filepath) as img:
            img_width, img_height = img.size
            
            # Validate crop boundaries
            if (crop_x < 0 or crop_y < 0 or 
                crop_x + crop_width > img_width or 
                crop_y + crop_height > img_height):
                return jsonify({'success': False, 'error': 'Crop area is outside image boundaries'}), 400
            
            # Perform crop
            cropped_img = img.crop((crop_x, crop_y, crop_x + crop_width, crop_y + crop_height))
            
            # Handle image format conversion for better compatibility
            original_filename = filename.split('.')[0]
            ext = filename.split('.')[-1].lower()
            
            if cropped_img.mode in ('RGBA', 'LA', 'P') and ext.lower() in ['jpg', 'jpeg']:
                background = Image.new('RGB', cropped_img.size, (255, 255, 255))
                if cropped_img.mode == 'P':
                    cropped_img = cropped_img.convert('RGBA')
                background.paste(cropped_img, mask=cropped_img.split()[-1] if cropped_img.mode == 'RGBA' else None)
                cropped_img = background
            
            # Generate filename for cropped image
            cropped_filename = f"{original_filename}_cropped.{ext}"
            cropped_path = os.path.join(UPLOAD_FOLDER, cropped_filename)
            
            # Save cropped image
            save_format = get_proper_format(ext)
            if save_format == 'JPEG':
                cropped_img.save(cropped_path, format=save_format, quality=95, optimize=True)
            else:
                cropped_img.save(cropped_path, format=save_format, optimize=True)
        
        return jsonify({
            'success': True,
            'cropped_filename': cropped_filename,
            'cropped_url': f'/image/{cropped_filename}',
            'original_size': {'width': img_width, 'height': img_height},
            'cropped_size': {'width': crop_width, 'height': crop_height},
            'crop_area': {'x': crop_x, 'y': crop_y, 'width': crop_width, 'height': crop_height}
        })
    
    except ValueError as e:
        return jsonify({'success': False, 'error': 'Invalid crop parameters - must be integers'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error processing crop: {str(e)}'}), 500

@app.route('/download_cropped/<filename>')
def download_cropped_image(filename):
    """Download the cropped image"""
    try:  
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if not os.path.exists(filepath):
            return jsonify({'error': 'File not found'}), 404
        
        # Get original filename for download
        if '_cropped.' in filename:
            original_name = filename.replace('_cropped.', '_final.')
        else:
            original_name = f"cropped_{filename}"
        
        return send_file(
            filepath,
            as_attachment=True,
            download_name=original_name
        )
    
    except Exception as e:
        return jsonify({'error': f'Error downloading file: {str(e)}'}), 500


@app.route('/upload', methods=['GET'])
def upload_page():
    """Serve the upload page"""
    cleanup_files()
    try:
        return render_template('upload.html')
    except:
        return jsonify({'message': 'Upload page - upload.html template not found'}), 404

@app.route('/flip', methods=['GET'])
def flip_page():
    """Serve the flip tool page"""
    try:
        return render_template('flip.html')
    except:
        return jsonify({'message': 'Flip page - flip.html template not found'}), 404

@app.route('/upload_image', methods=['POST'])
def upload_image():
    """Handle image upload and return image data for flip page"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        if not file.filename or not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Invalid file type. Supported formats: PNG, JPG, JPEG, GIF, BMP, WEBP'}), 400
        
        # Save uploaded file
        original_filename = secure_filename(file.filename)
        ext = original_filename.rsplit('.', 1)[1].lower()
        unique_id = str(uuid.uuid4())
        saved_filename = f"{unique_id}.{ext}"
        filepath = os.path.join(UPLOAD_FOLDER, saved_filename)
        file.save(filepath)
        
        # Get image dimensions
        with Image.open(filepath) as img:
            width, height = img.size
        
        return jsonify({
            'success': True,
            'filename': saved_filename,
            'original_filename': original_filename,
            'image_url': f'/image/{saved_filename}',
            'dimensions': {'width': width, 'height': height}
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error uploading image: {str(e)}'}), 500

@app.route('/flip_image', methods=['POST'])
def flip_image_tool():
    """Handle image flipping with horizontal and vertical options"""
    try:
        data = request.get_json()
        
        if not data or 'filename' not in data:
            return jsonify({'success': False, 'error': 'No filename provided'}), 400
        
        filename = data['filename']
        flip_horizontal = data.get('flip_horizontal', False)
        flip_vertical = data.get('flip_vertical', False)
        
        # Validate file exists
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if not os.path.exists(filepath):
            return jsonify({'success': False, 'error': 'Image file not found'}), 404
        
        # Open and flip image
        with Image.open(filepath) as img:
            processed_img = img.copy()
            
            # Apply flips
            if flip_horizontal:
                processed_img = processed_img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            
            if flip_vertical:
                processed_img = processed_img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            
            # Generate new filename for flipped image
            base_name = filename.rsplit('.', 1)[0]
            ext = filename.rsplit('.', 1)[1]
            flipped_filename = f"{base_name}_flipped.{ext}"
            flipped_path = os.path.join(UPLOAD_FOLDER, flipped_filename)
            
            # Save flipped image
            save_format = get_proper_format(ext)
            if save_format == 'JPEG':
                processed_img.save(flipped_path, format=save_format, quality=95, optimize=True)
            else:
                processed_img.save(flipped_path, format=save_format, optimize=True)
        
        return jsonify({
            'success': True,
            'flipped_filename': flipped_filename,
            'flipped_url': f'/image/{flipped_filename}',
            'flips_applied': {
                'horizontal': flip_horizontal,
                'vertical': flip_vertical
            }
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error flipping image: {str(e)}'}), 500

@app.route('/download_flipped/<filename>')
def download_flipped_image(filename):
    """Download the flipped image"""
    try:
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if not os.path.exists(filepath):
            return jsonify({'error': 'File not found'}), 404
        
        # Get original filename without the _flipped suffix
        original_name = filename.replace('_flipped', '_final')
        
        return send_file(
            filepath,
            as_attachment=True,
            download_name=original_name
        )
    
    except Exception as e:
        return jsonify({'error': f'Error downloading file: {str(e)}'}), 500
    
@app.route('/thumbnailupload')
def thumbnailupload():
    """Serve the upload page"""
    cleanup_files()
    try:
        return render_template('thumbnailupload.html')
    except:
        return jsonify({'message': 'Upload page - thumbnailupload.html template not found'}), 404

@app.route('/thumbnail')
def thumbnail_page():
    """Serve the thumbnail tool page"""
    try:
        return render_template('thumbnail.html')
    except:
        return jsonify({'message': 'Thumbnail page - thumbnail.html template not found'}), 404

@app.route('/upload_image', methods=['POST'])
def uploadimage():
    """Handle image upload and return image data for thumbnail page"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        if not file.filename or not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Invalid file type. Supported formats: PNG, JPG, JPEG, GIF, BMP, WEBP'}), 400
        
        # Save uploaded file
        original_filename = secure_filename(file.filename)
        ext = original_filename.rsplit('.', 1)[1].lower()
        unique_id = str(uuid.uuid4())
        saved_filename = f"{unique_id}.{ext}"
        filepath = os.path.join(UPLOAD_FOLDER, saved_filename)
        file.save(filepath)
        
        # Get image dimensions
        with Image.open(filepath) as img:
            width, height = img.size
        
        return jsonify({
            'success': True,
            'filename': saved_filename,
            'original_filename': original_filename,
            'image_url': f'/image/{saved_filename}',
            'dimensions': {'width': width, 'height': height}
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error uploading image: {str(e)}'}), 500

@app.route('/generate_thumbnail', methods=['POST'])
def generate_thumbnail():
    """Handle thumbnail generation with specified dimensions"""
    try:
        data = request.get_json()
        
        if not data or 'filename' not in data:
            return jsonify({'success': False, 'error': 'No filename provided'}), 400
        
        filename = data['filename']
        width = data.get('width')
        height = data.get('height')
        
        # Validate dimensions
        if not width or not height or width <= 0 or height <= 0:
            return jsonify({'success': False, 'error': 'Invalid dimensions provided'}), 400
        
        if width > 2000 or height > 2000:
            return jsonify({'success': False, 'error': 'Maximum dimensions are 2000x2000 pixels'}), 400
        
        # Validate file exists
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if not os.path.exists(filepath):
            return jsonify({'success': False, 'error': 'Image file not found'}), 404
        
        # Open and resize image
        with Image.open(filepath) as img:
            # Convert to RGB if necessary (for JPEG compatibility)
            if img.mode in ('RGBA', 'P'):
                # For transparent images, create white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Create thumbnail using high-quality resampling
            thumbnail_img = img.resize((width, height), Image.Resampling.LANCZOS)
            
            # Generate new filename for thumbnail
            base_name = filename.rsplit('.', 1)[0]
            ext = filename.rsplit('.', 1)[1]
            thumbnail_filename = f"{base_name}_thumbnail_{width}x{height}.{ext}"
            thumbnail_path = os.path.join(UPLOAD_FOLDER, thumbnail_filename)
            
            # Save thumbnail
            save_format = get_proper_format(ext)
            if save_format == 'JPEG':
                thumbnail_img.save(thumbnail_path, format=save_format, quality=95, optimize=True)
            else:
                thumbnail_img.save(thumbnail_path, format=save_format, optimize=True)
        
        return jsonify({
            'success': True,
            'thumbnail_filename': thumbnail_filename,
            'thumbnail_url': f'/image/{thumbnail_filename}',
            'dimensions': {
                'width': width,
                'height': height
            },
            'original_filename': filename
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error generating thumbnail: {str(e)}'}), 500

@app.route('/image/<filename>')
def serve_image(filename):
    """Serve uploaded images"""
    try:
        return send_from_directory(UPLOAD_FOLDER, filename)
    except FileNotFoundError:
        return jsonify({'error': 'Image not found'}), 404

@app.route('/download_thumbnail/<filename>')
def download_thumbnail(filename):
    """Download the generated thumbnail"""
    try:
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if not os.path.exists(filepath):
            return jsonify({'error': 'File not found'}), 404
        
        # Get a clean filename for download
        # Remove the UUID prefix and keep the thumbnail suffix
        if '_thumbnail_' in filename:
            parts = filename.split('_thumbnail_')
            if len(parts) >= 2:
                dimensions_part = parts[1]
                ext = dimensions_part.split('.')[-1]
                clean_name = f"thumbnail_{dimensions_part}"
            else:
                clean_name = filename
        else:
            clean_name = filename
        
        return send_file(
            filepath,
            as_attachment=True,
            download_name=clean_name
        )
    
    except Exception as e:
        return jsonify({'error': f'Error downloading file: {str(e)}'}), 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'thumbnail-tool'})

@app.errorhandler(413)
def too_large(e):
    """Handle file too large error"""
    return jsonify({'success': False, 'error': 'File too large. Maximum size is 16MB.'}), 413

@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors"""
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    """Handle 500 errors"""
    return jsonify({'error': 'Internal server error'}), 500

# Background Removal Tool Routes

@app.route('/backgroundupload')
def background_upload_page():
    """Serve the background removal upload page"""
    cleanup_files()
    try:
        return render_template('backgroundupload.html')
    except:
        return jsonify({'message': 'Background upload page - backgroundupload.html template not found'}), 404

@app.route('/backgroundtool')
def background_tool_page():
    """Serve the background removal tool page"""
    try:
        return render_template('backgroundtool.html')
    except:
        return jsonify({'message': 'Background tool page - backgroundtool.html template not found'}), 404

@app.route('/upload_image_for_background', methods=['POST'])
def upload_image_for_background():
    """Handle image upload for background removal tool"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        if not file.filename or not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Invalid file type. Supported formats: PNG, JPG, JPEG, GIF, BMP, WEBP'}), 400
        
        # Validate file size (10MB limit)
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)  # Reset file pointer
        
        max_size = 10 * 1024 * 1024  # 10MB
        if file_size > max_size:
            return jsonify({'success': False, 'error': 'File size must be less than 10MB'}), 400
        
        # Save uploaded file
        original_filename = secure_filename(file.filename)
        ext = original_filename.rsplit('.', 1)[1].lower()
        unique_id = str(uuid.uuid4())
        saved_filename = f"bg_remove_{unique_id}.{ext}"
        filepath = os.path.join(UPLOAD_FOLDER, saved_filename)
        file.save(filepath)
        
        # Get image dimensions
        with Image.open(filepath) as img:
            width, height = img.size
        
        return jsonify({
            'success': True,
            'filename': saved_filename,
            'original_filename': original_filename,
            'image_url': f'/image/{saved_filename}',
            'dimensions': {'width': width, 'height': height}
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error uploading image: {str(e)}'}), 500

@app.route('/remove_background', methods=['POST'])
def remove_background():
    """Process background removal using rembg library"""
    try:
        data = request.get_json()
        
        if not data or 'filename' not in data:
            return jsonify({'success': False, 'error': 'No filename provided'}), 400
        
        filename = data['filename']
        
        # Validate file exists
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if not os.path.exists(filepath):
            return jsonify({'success': False, 'error': 'Image file not found'}), 404
        
        # Process background removal
        with open(filepath, 'rb') as input_file:
            input_data = input_file.read()
        
        # Remove background using rembg
        output_data = remove(input_data)
        
        # Generate new filename for processed image
        base_name = filename.rsplit('.', 1)[0]
        processed_filename = f"{base_name}_no_bg.png"  # Always save as PNG to preserve transparency
        processed_path = os.path.join(UPLOAD_FOLDER, processed_filename)
        
        # Save processed image
        with open(processed_path, 'wb') as output_file:
            output_file.write(output_data)
        
        # Get processed image dimensions
        with Image.open(processed_path) as img:
            processed_width, processed_height = img.size
        
        return jsonify({
            'success': True,
            'processed_filename': processed_filename,
            'processed_url': f'/image/{processed_filename}',
            'original_filename': filename,
            'dimensions': {
                'width': processed_width,
                'height': processed_height
            }
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error removing background: {str(e)}'}), 500

@app.route('/download_background_removed/<filename>')
def download_background_removed(filename):
    """Download the background-removed image"""
    try:
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if not os.path.exists(filepath):
            return jsonify({'error': 'File not found'}), 404
        
        # Get a clean filename for download
        if '_no_bg.' in filename:
            # Extract original name and add descriptive suffix
            original_part = filename.split('_no_bg.')[0]
            # Remove UUID prefix if present
            if 'bg_remove_' in original_part:
                clean_name = f"background_removed.png"
            else:
                clean_name = f"{original_part}_background_removed.png"
        else:
            clean_name = f"background_removed_{filename}"
        
        return send_file(
            filepath,
            as_attachment=True,
            download_name=clean_name,
            mimetype='image/png'
        )
    
    except Exception as e:
        return jsonify({'error': f'Error downloading file: {str(e)}'}), 500
    


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)