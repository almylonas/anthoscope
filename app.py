from flask import Flask, render_template, request, jsonify
import ee
import json
from datetime import datetime, timedelta

app = Flask(__name__)

# Initialize Earth Engine
ee_initialized = False
init_error = None

try:
    ee.Initialize(project='nsa-agroai')
    ee_initialized = True
    print("✓ Earth Engine initialized successfully")
except Exception as e:
    init_error = str(e)
    print(f"✗ Earth Engine initialization error: {e}")
    print("Please run 'earthengine authenticate' in your terminal first")
    ee_initialized = False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'ee_initialized': ee_initialized,
        'error': init_error if not ee_initialized else None
    })

@app.route('/get-ndvi-tile-url', methods=['POST'])
def get_ndvi_tile_url():
    """Generate a tile URL for NDVI visualization"""
    print("📡 Received request for NDVI tile URL")
    
    if not ee_initialized:
        print("✗ Earth Engine not initialized")
        return jsonify({'error': 'Earth Engine not initialized. Please authenticate first.'}), 500
    
    try:
        data = request.get_json()
        print(f"Request data: {data}")
        
        target_date = data.get('target_date')
        
        if not target_date:
            return jsonify({'error': 'No target date provided'}), 400
        
        print(f"Processing date: {target_date}")
        
        # Parse target date and create a search window (±30 days)
        target = ee.Date(target_date)
        start = target.advance(-30, 'day')
        end = target.advance(30, 'day')
        
        # Get MODIS NDVI data
        modis = ee.ImageCollection('MODIS/061/MOD13Q1') \
            .select('NDVI') \
            .filterDate(start, end)
        
        collection_size = modis.size().getInfo()
        print(f"Found {collection_size} images")
        
        if collection_size == 0:
            return jsonify({'error': 'No MODIS data available'}), 400
        
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
        
        print(f"Using image from: {date_str}")
        
        # Define visualization parameters with a color palette
        vis_params = {
            'min': 0,
            'max': 1,
            'palette': ['#d73027', '#f46d43', '#fdae61', '#fee08b', '#d9ef8b', '#a6d96a', '#66bd63', '#1a9850']
        }
        
        # Get map ID
        map_id = ndvi_scaled.getMapId(vis_params)
        
        print(f"✓ Tile URL generated successfully")
        
        return jsonify({
            'tile_url': map_id['tile_fetcher'].url_format,
            'date': date_str
        })
        
    except Exception as e:
        print(f"✗ Error in get_ndvi_tile_url: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/calculate-ndvi', methods=['POST'])
def calculate_ndvi():
    print("📡 Received request for NDVI calculation")
    
    if not ee_initialized:
        print("✗ Earth Engine not initialized")
        return jsonify({'error': 'Earth Engine not initialized. Please authenticate first.'}), 500
    
    try:
        data = request.get_json()
        geometry = data.get('geometry')
        target_date = data.get('target_date')
        
        if not geometry:
            return jsonify({'error': 'No geometry provided'}), 400
        
        if not target_date:
            return jsonify({'error': 'No target date provided'}), 400
        
        print(f"Calculating NDVI for date: {target_date}")
        
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
        print(f"Found {collection_size} images")
        
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
        
        print(f"✓ NDVI calculated: {ndvi_scaled:.4f}")
        
        return jsonify({
            'ndvi': ndvi_scaled,
            'date': date_str,
            'days_difference': days_diff,
            'satellite': 'MODIS Terra',
            'product': 'MOD13Q1'
        })
        
    except Exception as e:
        print(f"✗ Error in calculate_ndvi: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/get-ndvi-history', methods=['POST'])
def get_ndvi_history():
    """Get NDVI time series for the past year"""
    print("📡 Received request for NDVI history")
    
    if not ee_initialized:
        print("✗ Earth Engine not initialized")
        return jsonify({'error': 'Earth Engine not initialized. Please authenticate first.'}), 500
    
    try:
        data = request.get_json()
        geometry = data.get('geometry')
        target_date = data.get('target_date')
        
        if not geometry:
            return jsonify({'error': 'No geometry provided'}), 400
        
        if not target_date:
            return jsonify({'error': 'No target date provided'}), 400
        
        print(f"Fetching history for date: {target_date}")
        
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
        print(f"Found {collection_size} images in the past year")
        
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
        
        print(f"Processing {len(time_series)} data points")
        
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
        
        print(f"✓ Found {len(blooms)} blooming events")
        
        return jsonify({
            'time_series': time_series,
            'blooms': blooms
        })
        
    except Exception as e:
        print(f"✗ Error in get_ndvi_history: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 Starting Flask NDVI Application")
    print("="*50)
    if ee_initialized:
        print("✓ Earth Engine: Ready")
    else:
        print("✗ Earth Engine: Not initialized")
        print("  Run: earthengine authenticate")
    print("="*50 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)