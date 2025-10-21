from flask import Flask, render_template, request, jsonify
import ee
import json
from datetime import datetime, timedelta
import os
import logging
import traceback

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize Earth Engine
ee_initialized = False
init_error = None
credentials_info = {}

try:
    logger.info("🔧 Starting Earth Engine initialization...")
    
    # Check individual environment variables first
    env_vars = {
        'type': os.environ.get('type'),
        'project_id': os.environ.get('project_id'),
        'private_key_id': os.environ.get('private_key_id'),
        'private_key': os.environ.get('private_key'),
        'client_email': os.environ.get('client_email'),
        'client_id': os.environ.get('client_id'),
        'token_uri': os.environ.get('token_uri'),
    }
    
    logger.info(f"Environment variables found: { {k: '✓' if v else '✗' for k, v in env_vars.items()} }")
    
    # Check if we have the minimum required variables
    required_vars = ['client_email', 'private_key', 'project_id']
    missing_vars = [var for var in required_vars if not env_vars.get(var)]
    
    if missing_vars:
        error_msg = f"Missing required environment variables: {missing_vars}"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    # Build credentials dictionary
    credentials_dict = {
        'type': env_vars['type'],
        'project_id': env_vars['project_id'],
        'private_key_id': env_vars['private_key_id'],
        'private_key': env_vars['private_key'],
        'client_email': env_vars['client_email'],
        'client_id': env_vars['client_id'],
        'auth_uri': os.environ.get('auth_uri', 'https://accounts.google.com/o/oauth2/auth'),
        'token_uri': env_vars['token_uri'],
        'auth_provider_x509_cert_url': os.environ.get('auth_provider_x509_cert_url', 'https://www.googleapis.com/oauth2/v1/certs'),
        'client_x509_cert_url': os.environ.get('client_x509_cert_url', ''),
        'universe_domain': os.environ.get('universe_domain', 'googleapis.com')
    }
    
    logger.info("Building service account credentials...")
    
    # Create service account credentials
    credentials = ee.ServiceAccountCredentials(
        email=credentials_dict['client_email'],
        key_data=credentials_dict['private_key']
    )
    
    logger.info("Initializing Earth Engine...")
    
    # Initialize Earth Engine
    ee.Initialize(credentials=credentials, project=credentials_dict['project_id'])
    
    ee_initialized = True
    credentials_info = {
        'client_email': credentials_dict['client_email'],
        'project_id': credentials_dict['project_id'],
        'private_key_id': credentials_dict['private_key_id'][:10] + '...' if credentials_dict['private_key_id'] else None
    }
    
    logger.info("✅ Earth Engine initialized successfully!")
    
except Exception as e:
    init_error = str(e)
    ee_initialized = False
    logger.error(f"❌ Earth Engine initialization failed: {e}")
    logger.error(traceback.format_exc())

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health', methods=['GET'])
def health():
    """Comprehensive health check endpoint"""
    ee_test_success = False
    ee_test_error = None
    ee_test_details = None
    
    if ee_initialized:
        try:
            # Test 1: Simple image creation
            test_image = ee.Image(1)
            test_info = test_image.getInfo()
            ee_test_success = True
            ee_test_details = "Simple image test passed"
            
            # Test 2: Try to access MODIS collection
            try:
                modis_test = ee.ImageCollection('MODIS/061/MOD13Q1').limit(1)
                modis_size = modis_test.size().getInfo()
                ee_test_details = f"Simple image and MODIS access passed. Collection size: {modis_size}"
            except Exception as modis_e:
                ee_test_details = f"Simple image passed but MODIS failed: {str(modis_e)}"
                
        except Exception as e:
            ee_test_error = str(e)
            ee_test_details = f"Test failed: {str(e)}"
    
    health_status = {
        'status': 'ok',
        'ee_initialized': ee_initialized,
        'ee_test_success': ee_test_success,
        'ee_test_details': ee_test_details,
        'ee_test_error': ee_test_error,
        'init_error': init_error,
        'credentials': credentials_info,
        'environment': 'railway',
        'timestamp': datetime.now().isoformat()
    }
    
    logger.info(f"Health check: {health_status}")
    return jsonify(health_status)

@app.route('/debug/full', methods=['GET'])
def debug_full():
    """Full debug information"""
    env_info = {
        'railway_environment': bool(os.environ.get('RAILWAY_ENVIRONMENT')),
        'port': os.environ.get('PORT'),
        'all_ee_vars_present': all([
            os.environ.get('type'),
            os.environ.get('project_id'), 
            os.environ.get('private_key'),
            os.environ.get('client_email')
        ])
    }
    
    # Test Earth Engine functionality
    ee_capabilities = {}
    if ee_initialized:
        try:
            # Test basic functionality
            ee_capabilities['basic_image'] = True
            ee_capabilities['modis_access'] = bool(ee.ImageCollection('MODIS/061/MOD13Q1').size().getInfo() > 0)
            
            # Test tile generation
            try:
                test_ndvi = ee.Image(1)
                map_id = test_ndvi.getMapId({'min': 0, 'max': 1})
                ee_capabilities['tile_generation'] = True
            except Exception as e:
                ee_capabilities['tile_generation'] = False
                ee_capabilities['tile_error'] = str(e)
                
        except Exception as e:
            ee_capabilities['error'] = str(e)
    
    return jsonify({
        'earth_engine': {
            'initialized': ee_initialized,
            'error': init_error,
            'credentials': credentials_info,
            'capabilities': ee_capabilities
        },
        'environment': env_info,
        'system': {
            'python_version': os.sys.version,
            'working_directory': os.getcwd()
        }
    })

@app.route('/test-ndvi-tile', methods=['GET'])
def test_ndvi_tile():
    """Test NDVI tile generation with fixed parameters"""
    logger.info("🧪 Testing NDVI tile generation...")
    
    if not ee_initialized:
        return jsonify({'error': f'Earth Engine not initialized: {init_error}'}), 500
    
    try:
        # Use a fixed date for testing
        target_date = '2023-06-01'
        logger.info(f"Testing with date: {target_date}")
        
        # Parse target date and create a search window
        target = ee.Date(target_date)
        start = target.advance(-30, 'day')
        end = target.advance(30, 'day')
        
        logger.info("Fetching MODIS data...")
        
        # Get MODIS NDVI data
        modis = ee.ImageCollection('MODIS/061/MOD13Q1') \
            .select('NDVI') \
            .filterDate(start, end)
        
        collection_size = modis.size().getInfo()
        logger.info(f"Found {collection_size} images")
        
        if collection_size == 0:
            return jsonify({'error': 'No MODIS data available for test date'}), 400
        
        # Find closest image
        def add_date_diff(image):
            diff = ee.Number(image.get('system:time_start')).subtract(target.millis()).abs()
            return image.set('date_diff', diff)
        
        modis_with_diff = modis.map(add_date_diff)
        closest_image = modis_with_diff.sort('date_diff').first()
        
        # Scale NDVI
        ndvi_scaled = closest_image.divide(10000.0)
        
        # Get image date
        date_millis = closest_image.get('system:time_start').getInfo()
        image_date = datetime.fromtimestamp(date_millis / 1000)
        date_str = image_date.strftime('%Y-%m-%d')
        
        logger.info(f"Using image from: {date_str}")
        
        # Visualization parameters
        vis_params = {
            'min': 0,
            'max': 1,
            'palette': ['#d73027', '#f46d43', '#fdae61', '#fee08b', '#d9ef8b', '#a6d96a', '#66bd63', '#1a9850']
        }
        
        logger.info("Generating tile URL...")
        
        # Get map ID
        map_id = ndvi_scaled.getMapId(vis_params)
        tile_url = map_id['tile_fetcher'].url_format
        
        logger.info(f"✅ Tile URL generated successfully: {tile_url[:100]}...")
        
        return jsonify({
            'success': True,
            'tile_url': tile_url,
            'date': date_str,
            'test_date': target_date,
            'images_found': collection_size
        })
        
    except ee.EEException as e:
        logger.error(f"Earth Engine error in test: {str(e)}")
        return jsonify({'error': f'Earth Engine error: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Unexpected error in test: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Test failed: {str(e)}'}), 500

@app.route('/get-ndvi-tile-url', methods=['POST'])
def get_ndvi_tile_url():
    """Generate a tile URL for NDVI visualization"""
    logger.info("📡 Received request for NDVI tile URL")
    
    if not ee_initialized:
        logger.error("Earth Engine not initialized")
        return jsonify({'error': f'Earth Engine not initialized: {init_error}'}), 500
    
    try:
        data = request.get_json()
        if not data:
            logger.error("No JSON data in request")
            return jsonify({'error': 'No JSON data provided'}), 400
            
        target_date = data.get('target_date')
        
        if not target_date:
            logger.error("No target date provided")
            return jsonify({'error': 'No target date provided'}), 400
        
        logger.info(f"Processing date: {target_date}")
        
        # Parse target date and create a search window (±30 days)
        target = ee.Date(target_date)
        start = target.advance(-30, 'day')
        end = target.advance(30, 'day')
        
        logger.info("Fetching MODIS data...")
        
        # Get MODIS NDVI data
        modis = ee.ImageCollection('MODIS/061/MOD13Q1') \
            .select('NDVI') \
            .filterDate(start, end)
        
        collection_size = modis.size().getInfo()
        logger.info(f"Found {collection_size} images")
        
        if collection_size == 0:
            logger.error("No MODIS data found for date range")
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
        
        logger.info("Generating map ID...")
        
        # Get map ID
        map_id = ndvi_scaled.getMapId(vis_params)
        tile_url = map_id['tile_fetcher'].url_format
        
        logger.info("✅ Tile URL generated successfully")
        
        return jsonify({
            'tile_url': tile_url,
            'date': date_str,
            'success': True
        })
        
    except ee.EEException as e:
        logger.error(f"Earth Engine error: {str(e)}")
        return jsonify({'error': f'Earth Engine error: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
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
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
            
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
            'product': 'MOD13Q1',
            'success': True
        })
        
    except ee.EEException as e:
        logger.error(f"Earth Engine error: {str(e)}")
        return jsonify({'error': f'Earth Engine error: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
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
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
            
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
            'blooms': blooms,
            'success': True
        })
        
    except ee.EEException as e:
        logger.error(f"Earth Engine error: {str(e)}")
        return jsonify({'error': f'Earth Engine error: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

# Add a catch-all route for debugging
@app.route('/<path:path>')
def catch_all(path):
    return jsonify({
        'error': f'Route not found: /{path}',
        'available_routes': [
            'GET /',
            'GET /health', 
            'GET /debug/full',
            'GET /test-ndvi-tile',
            'POST /get-ndvi-tile-url',
            'POST /calculate-ndvi',
            'POST /get-ndvi-history'
        ]
    }), 404

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 Starting Flask NDVI Application - DEBUG VERSION")
    print("="*60)
    print(f"✅ Earth Engine Initialized: {ee_initialized}")
    if not ee_initialized:
        print(f"❌ Error: {init_error}")
    else:
        print(f"📧 Service Account: {credentials_info.get('client_email', 'Unknown')}")
        print(f"📁 Project: {credentials_info.get('project_id', 'Unknown')}")
    
    print("\n🔍 Available Endpoints:")
    print("  GET  /health           - Basic health check")
    print("  GET  /debug/full       - Detailed debug information") 
    print("  GET  /test-ndvi-tile   - Test NDVI tile generation")
    print("  POST /get-ndvi-tile-url - Generate NDVI tile URL")
    print("  POST /calculate-ndvi   - Calculate NDVI for area")
    print("  POST /get-ndvi-history - Get NDVI time series")
    print("="*60 + "\n")
    
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))