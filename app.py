from flask import Flask, render_template, request, jsonify
import ee
import json
from datetime import datetime, timedelta
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize Earth Engine
ee_initialized = False
init_error = None

try:
    # Check if running on Railway with service account
    ee_key_json = os.environ.get('EE_SERVICE_ACCOUNT_KEY')
    
    if ee_key_json:
        # Method 1: Single JSON environment variable
        logger.info("Found EE_SERVICE_ACCOUNT_KEY environment variable")
        
        try:
            credentials_dict = json.loads(ee_key_json)
            logger.info("Successfully parsed service account JSON")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse EE_SERVICE_ACCOUNT_KEY: {e}")
            raise Exception(f"Invalid JSON in EE_SERVICE_ACCOUNT_KEY: {e}")
        
    else:
        # Method 2: Individual environment variables
        logger.info("No EE_SERVICE_ACCOUNT_KEY found, checking individual variables")
        
        required_vars = [
            'type', 'project_id', 'private_key_id', 'private_key',
            'client_email', 'client_id', 'token_uri'
        ]
        
        missing_vars = [var for var in required_vars if not os.environ.get(var)]
        
        if missing_vars:
            logger.error(f"Missing required environment variables: {missing_vars}")
            raise Exception(f"Missing required environment variables: {missing_vars}")
        
        # Build credentials dictionary from individual variables
        credentials_dict = {
            'type': os.environ.get('type'),
            'project_id': os.environ.get('project_id'),
            'private_key_id': os.environ.get('private_key_id'),
            'private_key': os.environ.get('private_key'),
            'client_email': os.environ.get('client_email'),
            'client_id': os.environ.get('client_id'),
            'auth_uri': os.environ.get('auth_uri', 'https://accounts.google.com/o/oauth2/auth'),
            'token_uri': os.environ.get('token_uri'),
            'auth_provider_x509_cert_url': os.environ.get('auth_provider_x509_cert_url', 'https://www.googleapis.com/oauth2/v1/certs'),
            'client_x509_cert_url': os.environ.get('client_x509_cert_url'),
            'universe_domain': os.environ.get('universe_domain', 'googleapis.com')
        }
        logger.info("Built credentials from individual environment variables")
    
    # Validate required fields
    required_fields = ['client_email', 'private_key', 'project_id']
    for field in required_fields:
        if field not in credentials_dict or not credentials_dict[field]:
            logger.error(f"Missing required field in service account: {field}")
            raise Exception(f"Service account missing required field: {field}")
    
    # Initialize with service account
    credentials = ee.ServiceAccountCredentials(
        email=credentials_dict['client_email'],
        key_data=credentials_dict['private_key']
    )
    ee.Initialize(credentials=credentials, project=credentials_dict['project_id'])
    logger.info("✓ Earth Engine initialized with service account")
    ee_initialized = True
        
except Exception as e:
    init_error = str(e)
    logger.error(f"✗ Earth Engine initialization error: {e}")
    ee_initialized = False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    # Test EE connectivity
    ee_test_success = False
    ee_test_error = None
    
    if ee_initialized:
        try:
            # Simple test to verify EE is working
            test_image = ee.Image(1)
            test_info = test_image.getInfo()
            ee_test_success = True
        except Exception as e:
            ee_test_error = str(e)
    
    health_status = {
        'status': 'ok',
        'ee_initialized': ee_initialized,
        'ee_test_success': ee_test_success,
        'init_error': init_error,
        'ee_test_error': ee_test_error,
        'environment': 'railway' if os.environ.get('EE_SERVICE_ACCOUNT_KEY') or os.environ.get('client_email') else 'local'
    }
    logger.info(f"Health check: {health_status}")
    return jsonify(health_status)

@app.route('/debug/env', methods=['GET'])
def debug_env():
    """Debug endpoint to check environment variables (without sensitive data)"""
    env_vars = {
        'EE_SERVICE_ACCOUNT_KEY_exists': bool(os.environ.get('EE_SERVICE_ACCOUNT_KEY')),
        'type_exists': bool(os.environ.get('type')),
        'project_id_exists': bool(os.environ.get('project_id')),
        'private_key_id_exists': bool(os.environ.get('private_key_id')),
        'private_key_exists': bool(os.environ.get('private_key')),
        'client_email_exists': bool(os.environ.get('client_email')),
        'client_id_exists': bool(os.environ.get('client_id')),
        'token_uri_exists': bool(os.environ.get('token_uri')),
        'railway_environment': bool(os.environ.get('RAILWAY_ENVIRONMENT')),
    }
    return jsonify(env_vars)

@app.route('/get-ndvi-tile-url', methods=['POST'])
def get_ndvi_tile_url():
    """Generate a tile URL for NDVI visualization"""
    logger.info("📡 Received request for NDVI tile URL")
    
    if not ee_initialized:
        logger.error("Earth Engine not initialized")
        return jsonify({'error': f'Earth Engine not initialized: {init_error}'}), 500
    
    try:
        data = request.get_json()
        logger.info(f"Request data: {data}")
        
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
            
        target_date = data.get('target_date')
        
        if not target_date:
            return jsonify({'error': 'No target date provided'}), 400
        
        logger.info(f"Processing date: {target_date}")
        
        # Parse target date and create a search window (±30 days)
        target = ee.Date(target_date)
        start = target.advance(-30, 'day')
        end = target.advance(30, 'day')
        
        # Get MODIS NDVI data
        modis = ee.ImageCollection('MODIS/061/MOD13Q1') \
            .select('NDVI') \
            .filterDate(start, end)
        
        collection_size = modis.size().getInfo()
        logger.info(f"Found {collection_size} images")
        
        if collection_size == 0:
            return jsonify({'error': 'No MODIS data available for the specified date range'}), 400
        
        # Find the image closest to the target date
        def add_date_diff(image):
            diff = ee.Number(image.get('system:time_start')).subtract(target.millis()).abs()
            return image.set('date_diff', diff)
        
        modis_with_diff = modis.map(add_date_diff)
        closest_image = modis_with_diff.sort('date_diff').first()
        
        # Scale NDVI to 0-1 range
        ndvi_scaled = closest_image.divide(10000.0)
        
        # Get the date of the closest image
        date_millis = closest_image.get('system:time_start').getInfo()
        image_date = datetime.fromtimestamp(date_millis / 1000)
        date_str = image_date.strftime('%Y-%m-%d')
        
        logger.info(f"Using image from: {date_str}")
        
        # Define visualization parameters with a color palette
        vis_params = {
            'min': 0,
            'max': 1,
            'palette': ['#d73027', '#f46d43', '#fdae61', '#fee08b', '#d9ef8b', '#a6d96a', '#66bd63', '#1a9850']
        }
        
        # Get map ID
        map_id = ndvi_scaled.getMapId(vis_params)
        
        logger.info("✓ Tile URL generated successfully")
        
        return jsonify({
            'tile_url': map_id['tile_fetcher'].url_format,
            'date': date_str
        })
        
    except ee.EEException as e:
        logger.error(f"Earth Engine error: {str(e)}")
        return jsonify({'error': f'Earth Engine error: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/calculate-ndvi', methods=['POST'])
def calculate_ndvi():
    logger.info("📡 Received request for NDVI calculation")
    
    if not ee_initialized:
        logger.error("Earth Engine not initialized")
        return jsonify({'error': f'Earth Engine not initialized: {init_error}'}), 500
    
    try:
        data = request.get_json()
        geometry = data.get('geometry')
        target_date = data.get('target_date')
        
        if not geometry:
            return jsonify({'error': 'No geometry provided'}), 400
        
        if not target_date:
            return jsonify({'error': 'No target date provided'}), 400
        
        logger.info(f"Calculating NDVI for date: {target_date}")
        
        # Convert GeoJSON geometry to Earth Engine geometry
        ee_geometry = ee.Geometry.Polygon(geometry['coordinates'])
        
        # Parse target date and create a search window (±30 days)
        target = ee.Date(target_date)
        start = target.advance(-30, 'day')
        end = target.advance(30, 'day')
        
        # Get MODIS NDVI data (MOD13Q1 - 250m 16-day NDVI)
        modis = ee.ImageCollection('MODIS/061/MOD13Q1') \
            .select('NDVI') \
            .filterBounds(ee_geometry) \
            .filterDate(start, end)
        
        # Check if collection is empty
        collection_size = modis.size().getInfo()
        logger.info(f"Found {collection_size} images")
        
        if collection_size == 0:
            return jsonify({'error': 'No MODIS data available within 30 days of the target date'}), 400
        
        # Find the image closest to the target date
        def add_date_diff(image):
            diff = ee.Number(image.get('system:time_start')).subtract(target.millis()).abs()
            return image.set('date_diff', diff)
        
        modis_with_diff = modis.map(add_date_diff)
        closest_image = modis_with_diff.sort('date_diff').first()
        
        # Get the date of the closest image
        date_millis = closest_image.get('system:time_start').getInfo()
        image_date = datetime.fromtimestamp(date_millis / 1000)
        date_str = image_date.strftime('%Y-%m-%d')
        
        # Calculate days difference
        target_datetime = datetime.strptime(target_date, '%Y-%m-%d')
        days_diff = (image_date - target_datetime).days
        
        # Calculate mean NDVI over the polygon
        ndvi_stats = closest_image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=ee_geometry,
            scale=250,
            maxPixels=1e9
        ).getInfo()
        
        ndvi_value = ndvi_stats.get('NDVI')
        
        if ndvi_value is None:
            return jsonify({'error': 'No NDVI data available for this area'}), 400
        
        # Scale NDVI value (MODIS stores values multiplied by 10000)
        ndvi_scaled = ndvi_value / 10000.0
        
        logger.info(f"✓ NDVI calculated: {ndvi_scaled:.4f}")
        
        return jsonify({
            'ndvi': ndvi_scaled,
            'date': date_str,
            'days_difference': days_diff,
            'satellite': 'MODIS Terra',
            'product': 'MOD13Q1'
        })
        
    except ee.EEException as e:
        logger.error(f"Earth Engine error: {str(e)}")
        return jsonify({'error': f'Earth Engine error: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/get-ndvi-history', methods=['POST'])
def get_ndvi_history():
    """Get NDVI time series for the past year"""
    logger.info("📡 Received request for NDVI history")
    
    if not ee_initialized:
        logger.error("Earth Engine not initialized")
        return jsonify({'error': f'Earth Engine not initialized: {init_error}'}), 500
    
    try:
        data = request.get_json()
        geometry = data.get('geometry')
        target_date = data.get('target_date')
        
        if not geometry:
            return jsonify({'error': 'No geometry provided'}), 400
        
        if not target_date:
            return jsonify({'error': 'No target date provided'}), 400
        
        logger.info(f"Fetching history for date: {target_date}")
        
        # Convert GeoJSON geometry to Earth Engine geometry
        ee_geometry = ee.Geometry.Polygon(geometry['coordinates'])
        
        # Parse target date and get one year of data
        target = ee.Date(target_date)
        start = target.advance(-365, 'day')
        
        # Get MODIS NDVI data for the past year
        modis = ee.ImageCollection('MODIS/061/MOD13Q1') \
            .select('NDVI') \
            .filterBounds(ee_geometry) \
            .filterDate(start, target)
        
        collection_size = modis.size().getInfo()
        logger.info(f"Found {collection_size} images in the past year")
        
        if collection_size == 0:
            return jsonify({'error': 'No MODIS data available for this area in the past year'}), 400
        
        # Calculate mean NDVI for each image
        def compute_mean(image):
            mean = image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=ee_geometry,
                scale=250,
                maxPixels=1e9
            ).get('NDVI')
            
            return ee.Feature(None, {
                'date': image.date().format('YYYY-MM-dd'),
                'ndvi': ee.Number(mean).divide(10000.0),
                'timestamp': image.date().millis()
            })
        
        # Map over collection and get results
        features = modis.map(compute_mean).getInfo()
        
        if not features or len(features['features']) == 0:
            return jsonify({'error': 'No NDVI data available for this area in the past year'}), 400
        
        # Extract time series data
        time_series = []
        for feature in features['features']:
            props = feature['properties']
            if props.get('ndvi') is not None:
                time_series.append({
                    'date': props['date'],
                    'ndvi': props['ndvi'],
                    'timestamp': props['timestamp']
                })
        
        # Sort by timestamp
        time_series.sort(key=lambda x: x['timestamp'])
        
        logger.info(f"Processing {len(time_series)} data points")
        
        # Detect blooming events (sudden increases in NDVI)
        blooms = []
        threshold = 0.15  # NDVI increase threshold for bloom detection
        
        for i in range(1, len(time_series)):
            current = time_series[i]['ndvi']
            previous = time_series[i-1]['ndvi']
            
            if current - previous > threshold:
                blooms.append({
                    'date': time_series[i]['date'],
                    'ndvi': current,
                    'increase': current - previous
                })
        
        logger.info(f"✓ Found {len(blooms)} blooming events")
        
        return jsonify({
            'time_series': time_series,
            'blooms': blooms
        })
        
    except ee.EEException as e:
        logger.error(f"Earth Engine error: {str(e)}")
        return jsonify({'error': f'Earth Engine error: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 Starting Flask NDVI Application")
    print("="*50)
    if ee_initialized:
        print("✓ Earth Engine: Ready")
        # Test EE connection
        try:
            test_image = ee.Image(1)
            test_info = test_image.getInfo()
            print("✓ Earth Engine: Test connection successful")
        except Exception as e:
            print(f"✗ Earth Engine: Test connection failed: {e}")
    else:
        print("✗ Earth Engine: Not initialized")
        print(f"  Error: {init_error}")
    print("Environment variables:")
    print(f"  - EE_SERVICE_ACCOUNT_KEY: {'✓' if os.environ.get('EE_SERVICE_ACCOUNT_KEY') else '✗'}")
    print(f"  - Individual vars: {'✓' if os.environ.get('client_email') else '✗'}")
    print("="*50 + "\n")
    
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))