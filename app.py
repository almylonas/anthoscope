from flask import Flask, render_template, request, jsonify
import ee
import json
from datetime import datetime, timedelta
import os
import logging
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize Earth Engine
ee_initialized = False
init_error = None

try:
    logger.info("🔧 Starting Earth Engine initialization...")
    
    # Get the service account JSON from environment variable
    ee_service_account_json = os.environ.get('EE_SERVICE_ACCOUNT_JSON')
    
    if not ee_service_account_json:
        logger.error("❌ EE_SERVICE_ACCOUNT_JSON environment variable not found")
        raise Exception("EE_SERVICE_ACCOUNT_JSON environment variable is required")
    
    logger.info("✓ Found EE_SERVICE_ACCOUNT_JSON environment variable")
    
    # Parse the JSON
    try:
        service_account_info = json.loads(ee_service_account_json)
        logger.info("✓ Successfully parsed service account JSON")
    except json.JSONDecodeError as e:
        logger.error(f"❌ Failed to parse service account JSON: {e}")
        raise Exception(f"Invalid JSON in EE_SERVICE_ACCOUNT_JSON: {e}")
    
    # Validate required fields
    required_fields = ['client_email', 'private_key', 'project_id']
    for field in required_fields:
        if field not in service_account_info:
            logger.error(f"❌ Missing required field in service account: {field}")
            raise Exception(f"Service account JSON missing required field: {field}")
    
    logger.info(f"✓ Service account for: {service_account_info['client_email']}")
    logger.info(f"✓ Project: {service_account_info['project_id']}")
    
    # Initialize Earth Engine with service account
    credentials = ee.ServiceAccountCredentials(
        email=service_account_info['client_email'],
        key_data=service_account_info['private_key']
    )
    
    ee.Initialize(credentials=credentials, project=service_account_info['project_id'])
    
    ee_initialized = True
    logger.info("✅ Earth Engine initialized successfully!")
    
except Exception as e:
    init_error = str(e)
    ee_initialized = False
    logger.error(f"❌ Earth Engine initialization failed: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    ee_test_success = False
    ee_test_error = None
    
    if ee_initialized:
        try:
            # Test Earth Engine connection
            test_image = ee.Image(1)
            test_info = test_image.getInfo()
            ee_test_success = True
        except Exception as e:
            ee_test_error = str(e)
    
    return jsonify({
        'status': 'ok',
        'ee_initialized': ee_initialized,
        'ee_test_success': ee_test_success,
        'ee_test_error': ee_test_error,
        'init_error': init_error,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/debug/env', methods=['GET'])
def debug_env():
    """Debug environment variables"""
    return jsonify({
        'ee_service_account_json_present': bool(os.environ.get('EE_SERVICE_ACCOUNT_JSON')),
        'environment': 'railway' if os.environ.get('RAILWAY_ENVIRONMENT') else 'local',
        'port': os.environ.get('PORT')
    })

@app.route('/get-ndvi-tile-url', methods=['POST'])
def get_ndvi_tile_url():
    """Generate a tile URL for NDVI visualization"""
    if not ee_initialized:
        return jsonify({'error': f'Earth Engine not initialized: {init_error}'}), 500
    
    try:
        data = request.get_json()
        target_date = data.get('target_date')
        
        if not target_date:
            return jsonify({'error': 'No target date provided'}), 400
        
        # Parse target date and create a search window (±30 days)
        target = ee.Date(target_date)
        start = target.advance(-30, 'day')
        end = target.advance(30, 'day')
        
        # Get MODIS NDVI data
        modis = ee.ImageCollection('MODIS/061/MOD13Q1') \
            .select('NDVI') \
            .filterDate(start, end)
        
        collection_size = modis.size().getInfo()
        
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
        
        # Define visualization parameters
        vis_params = {
            'min': 0,
            'max': 1,
            'palette': ['#d73027', '#f46d43', '#fdae61', '#fee08b', '#d9ef8b', '#a6d96a', '#66bd63', '#1a9850']
        }
        
        # Get map ID
        map_id = ndvi_scaled.getMapId(vis_params)
        
        return jsonify({
            'tile_url': map_id['tile_fetcher'].url_format,
            'date': date_str,
            'success': True
        })
        
    except Exception as e:
        logger.error(f"Error in get_ndvi_tile_url: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/calculate-ndvi', methods=['POST'])
def calculate_ndvi():
    if not ee_initialized:
        return jsonify({'error': f'Earth Engine not initialized: {init_error}'}), 500
    
    try:
        data = request.get_json()
        geometry = data.get('geometry')
        target_date = data.get('target_date')
        
        if not geometry:
            return jsonify({'error': 'No geometry provided'}), 400
        
        if not target_date:
            return jsonify({'error': 'No target date provided'}), 400
        
        # Convert GeoJSON geometry to Earth Engine geometry
        ee_geometry = ee.Geometry.Polygon(geometry['coordinates'])
        
        # Parse target date and create a search window (±30 days)
        target = ee.Date(target_date)
        start = target.advance(-30, 'day')
        end = target.advance(30, 'day')
        
        # Get MODIS NDVI data
        modis = ee.ImageCollection('MODIS/061/MOD13Q1') \
            .select('NDVI') \
            .filterBounds(ee_geometry) \
            .filterDate(start, end)
        
        collection_size = modis.size().getInfo()
        
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
        
        return jsonify({
            'ndvi': ndvi_scaled,
            'date': date_str,
            'days_difference': days_diff,
            'satellite': 'MODIS Terra',
            'product': 'MOD13Q1',
            'success': True
        })
        
    except Exception as e:
        logger.error(f"Error in calculate_ndvi: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/get-ndvi-history', methods=['POST'])
def get_ndvi_history():
    """Get NDVI time series for the past year"""
    if not ee_initialized:
        return jsonify({'error': f'Earth Engine not initialized: {init_error}'}), 500
    
    try:
        data = request.get_json()
        geometry = data.get('geometry')
        target_date = data.get('target_date')
        
        if not geometry:
            return jsonify({'error': 'No geometry provided'}), 400
        
        if not target_date:
            return jsonify({'error': 'No target date provided'}), 400
        
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
        
        # Detect blooming events (sudden increases in NDVI)
        blooms = []
        threshold = 0.15
        
        for i in range(1, len(time_series)):
            current = time_series[i]['ndvi']
            previous = time_series[i-1]['ndvi']
            
            if current - previous > threshold:
                blooms.append({
                    'date': time_series[i]['date'],
                    'ndvi': current,
                    'increase': current - previous
                })
        
        return jsonify({
            'time_series': time_series,
            'blooms': blooms,
            'success': True
        })
        
    except Exception as e:
        logger.error(f"Error in get_ndvi_history: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 Starting Flask NDVI Application")
    print("="*50)
    print(f"✅ Earth Engine Initialized: {ee_initialized}")
    if not ee_initialized:
        print(f"❌ Error: {init_error}")
    print("="*50 + "\n")
    
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))