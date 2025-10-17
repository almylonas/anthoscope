from flask import Flask, render_template_string, request, jsonify
import ee
import json
from datetime import datetime, timedelta

app = Flask(__name__)

# Initialize Earth Engine
# Then initialize with: ee.Initialize()
try:
    ee.Authenticate()
    ee.Initialize(project='nsa-agroai')
except Exception as e:
    print(f"Earth Engine initialization error: {e}")
    print("Please run 'earthengine authenticate' first")

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NDVI Calculator with MapLibre</title>
    <script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
    <link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet">
    <script src="https://unpkg.com/@mapbox/mapbox-gl-draw@1.4.3/dist/mapbox-gl-draw.js"></script>
    <link rel="stylesheet" href="https://unpkg.com/@mapbox/mapbox-gl-draw@1.4.3/dist/mapbox-gl-draw.css" type="text/css">
    <script src="https://unpkg.com/@turf/turf@6/turf.min.js"></script>
    <style>
        body {
            margin: 0;
            padding: 0;
        }
        #map {
            position: absolute;
            top: 0;
            bottom: 0;
            width: 100%;
        }
        .calculation-box {
            position: absolute;
            bottom: 40px;
            left: 10px;
            background-color: rgba(255, 255, 255, 0.95);
            padding: 15px;
            font-family: Arial, sans-serif;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            max-width: 320px;
        }
        .ndvi-info {
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid #ddd;
        }
        .loading {
            color: #0066cc;
            font-style: italic;
        }
        .error {
            color: #cc0000;
        }
        .success {
            color: #006600;
        }
        button {
            background-color: #0066cc;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            margin-top: 10px;
            width: 100%;
        }
        button:hover {
            background-color: #0052a3;
        }
        button:disabled {
            background-color: #cccccc;
            cursor: not-allowed;
        }
        .date-inputs {
            margin-top: 10px;
        }
        .date-inputs label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
            font-size: 0.9em;
        }
        .date-inputs input {
            width: 100%;
            padding: 6px;
            margin-bottom: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            box-sizing: border-box;
        }
    </style>
</head>
<body>
    <div id="map"></div>
    <div class="calculation-box">
        <p><strong>Draw a polygon on the map</strong></p>
        <div id="calculated-area"></div>
        <div class="date-inputs">
            <label for="target-date">Date of Interest:</label>
            <input type="date" id="target-date">
        </div>
        <button id="calculate-ndvi" disabled>Calculate NDVI</button>
        <div id="ndvi-result" class="ndvi-info"></div>
    </div>
    <script>
        const map = new maplibregl.Map({
            container: 'map',
            style: 'https://tiles.openfreemap.org/styles/bright',
            center: [22.965299092183916, 40.63759089777075],
            zoom: 9
        });

        const draw = new MapboxDraw({
            displayControlsDefault: true,
            controls: {
                polygon: true,
                trash: true
            },
            defaultMode: 'draw_polygon',
            styles: [
                // Polygon fill
                {
                    'id': 'gl-draw-polygon-fill',
                    'type': 'fill',
                    'filter': ['all', ['==', '$type', 'Polygon'], ['!=', 'mode', 'static']],
                    'paint': {
                        'fill-color': '#FF0000',
                        'fill-opacity': 0.5
                    }
                },
                {
                    'id': 'gl-draw-polygon-stroke-active',
                    'type': 'line',
                    'filter': ['all', ['==', '$type', 'Polygon'], ['!=', 'mode', 'static']],
                    'paint': {
                        'line-color': '#000000',
                        'line-width': 3
                    }
                }
            ]
        });

        map.on('load', function() {
            console.log('Map loaded successfully');
            
            map.addControl(draw, 'top-left');
            map.addControl(new maplibregl.NavigationControl(), 'top-right');
            map.addControl(new maplibregl.FullscreenControl(), 'top-right');
            map.addControl(new maplibregl.GeolocateControl({
                positionOptions: {
                    enableHighAccuracy: true
                },
                trackUserLocation: true
            }), 'top-right');

            // Set default date to today
            const today = new Date();
            document.getElementById('target-date').valueAsDate = today;

            let currentPolygon = null;

            map.on('draw.create', updateArea);
            map.on('draw.delete', updateArea);
            map.on('draw.update', updateArea);

            function updateArea(e) {
                const data = draw.getAll();
                const answer = document.getElementById('calculated-area');
                const ndviButton = document.getElementById('calculate-ndvi');
                const ndviResult = document.getElementById('ndvi-result');
                
                if (data.features.length > 0) {
                    currentPolygon = data.features[0];
                    const area = turf.area(data);
                    const rounded_area = (Math.round(area * 100) / 100000000).toFixed(3);
                    answer.innerHTML = `<p>Area: <strong>${rounded_area}</strong> km²</p>`;
                    ndviButton.disabled = false;
                    ndviResult.innerHTML = '';
                } else {
                    currentPolygon = null;
                    answer.innerHTML = '';
                    ndviButton.disabled = true;
                    ndviResult.innerHTML = '';
                }
            }

            document.getElementById('calculate-ndvi').addEventListener('click', async function() {
                if (!currentPolygon) return;
                
                const ndviResult = document.getElementById('ndvi-result');
                const button = this;
                const targetDate = document.getElementById('target-date').value;
                
                if (!targetDate) {
                    ndviResult.innerHTML = '<p class="error">Please select a date</p>';
                    return;
                }
                
                button.disabled = true;
                ndviResult.innerHTML = '<p class="loading">Finding closest MODIS data...</p>';
                
                try {
                    const response = await fetch('/calculate-ndvi', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            geometry: currentPolygon.geometry,
                            target_date: targetDate
                        })
                    });
                    
                    const data = await response.json();
                    
                    if (data.error) {
                        ndviResult.innerHTML = `<p class="error">Error: ${data.error}</p>`;
                    } else {
                        const ndviValue = data.ndvi.toFixed(4);
                        const date = data.date;
                        const daysDiff = data.days_difference;
                        ndviResult.innerHTML = `
                            <p class="success"><strong>NDVI: ${ndviValue}</strong></p>
                            <p style="font-size: 0.9em;">Image Date: ${date}</p>
                            <p style="font-size: 0.85em; color: #666;">
                                ${daysDiff === 0 ? 'Exact match' : `${Math.abs(daysDiff)} day${Math.abs(daysDiff) > 1 ? 's' : ''} ${daysDiff > 0 ? 'after' : 'before'} target date`}
                            </p>
                            <p style="font-size: 0.85em; color: #666;">
                                MODIS Terra 16-Day NDVI<br>
                                250m resolution
                            </p>
                        `;
                    }
                } catch (error) {
                    ndviResult.innerHTML = `<p class="error">Error: ${error.message}</p>`;
                } finally {
                    button.disabled = false;
                }
            });
        });
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/calculate-ndvi', methods=['POST'])
def calculate_ndvi():
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
        
        # Get MODIS NDVI data (MOD13Q1 - 250m 16-day NDVI)
        modis = ee.ImageCollection('MODIS/061/MOD13Q1') \
            .select('NDVI') \
            .filterBounds(ee_geometry) \
            .filterDate(start, end)
        
        # Check if collection is empty
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
            'product': 'MOD13Q1'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)