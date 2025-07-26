import streamlit as st
from geopy.geocoders import Nominatim
import folium
from streamlit_folium import st_folium
import requests
import geopandas as gpd
from shapely.geometry import shape, Point

# Futuristic theme
st.set_page_config(page_title="Network Connection Checker", layout="centered")
st.markdown("""
<style>
body { background-color: #1a1a1a; color: #ffffff; }
.stApp { background: linear-gradient(to right,#0f2027,#203a43,#2c5364); color: #ffffff; }
.stTextInput input { background-color: #333333; color: #ffffff; }
.stButton button { background-color: #00ffc3; color: black; font-weight: bold; }
.stAlert, .stWarning, .stSuccess, .stError {
    background-color: #333333;
    color: #ffffff;
}
header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# Title
st.title("🌐 Network Connection Checker")
st.write("Enter an address and overlay nearest UK Power Networks primary substation zone on the map and show the headroom availability.")

# Address input
address = st.text_input("📍 Enter Address")

if address:
    geolocator = Nominatim(user_agent="network_connection_checker")
    location = geolocator.geocode(address)

    if location:
        lat, lon = location.latitude, location.longitude
        st.success(f"Coordinates: Latitude {lat:.5f}, Longitude {lon:.5f}")

        # Create interactive folium map with OpenStreetMap tile layer
        m = folium.Map(location=[lat, lon], zoom_start=13, tiles="OpenStreetMap")
        folium.Marker([lat, lon], popup=address, icon=folium.Icon(color="lightgray")).add_to(m)

        # --- UK Power Networks overlay ---
        try:
            api_key = '6323514a7b6454baf9c65629725997c21161db1ae6a3fcbcc2654f03'
            url = (
                f"https://ukpowernetworks.opendatasoft.com/api/records/1.0/search/"
                f"?dataset=ukpn_primary_postcode_area"
                f"&rows=5000"
                f"&start=0"
                f"&geofilter.distance={lat},{lon},10000&apikey={api_key}"
            )

            headers = {
                'Authorization': f'Bearer {api_key}',
                'Accept': 'application/json'
            }

            r = requests.get(url, headers=headers, allow_redirects=True)
            r.raise_for_status()
            data = r.json()

            if data["nhits"] > 0:
                features = data["records"]
                geojson_data = {
                    "type": "FeatureCollection",
                    "features": []
                }

                for feature in features:
                    geometry = feature["geometry"]
                    geojson_data["features"].append({
                        "type": "Feature",
                        "properties": feature["fields"],
                        "geometry": geometry
                    })

                gdf = gpd.GeoDataFrame.from_features(geojson_data["features"])

                bounds = (lon - 0.1, lat - 0.1, lon + 0.1, lat + 0.1)
                subset = gdf.cx[bounds[0]:bounds[2], bounds[1]:bounds[3]]

                nearest_substation = None
                nearest_distance = float('inf')

                for _, row in subset.iterrows():
                    substation_location = row.geometry.centroid
                    distance = substation_location.distance(Point(lon, lat))

                    if distance < nearest_distance:
                        nearest_distance = distance
                        nearest_substation = row

                if nearest_substation is not None:
                    substation_name = nearest_substation['primary']
                    grid_site = nearest_substation.get('grid_site', 'N/A')
                    grid_supply_point = nearest_substation.get('grid_supply_point', 'N/A')
                    headroom = nearest_substation.get('demandrag', 'N/A')

                    st.write(f"🔌 **Nearest Primary Substation**: {substation_name}")
                    st.write(f"⚡ **Grid Site**: {grid_site}")
                    st.write(f"🌍 **Grid Supply Point**: {grid_supply_point}")
                    st.write(f"💡 **Headroom (Available Capacity)**: {headroom}")

                    polygon = shape(nearest_substation['geo_shape'])

                    folium.GeoJson(
                        polygon,
                        style_function=lambda x: {
                            'fillColor': 'blue',
                            'color': 'blue',
                            'weight': 2,
                            'fillOpacity': 0.4
                        }
                    ).add_to(m)

                    folium.Marker(
                        [nearest_substation.geometry.centroid.y, nearest_substation.geometry.centroid.x],
                        popup=f"{substation_name}: {grid_supply_point}",
                        icon=folium.Icon(color="red")
                    ).add_to(m)
                else:
                    st.warning("No primary substation found within the given area.")
            else:
                st.warning("No records found in the vicinity. Please try a different address or expand the search radius.")
        except Exception as e:
            st.error(f"Could not load UK Power Networks data: {e}")

        st_folium(m, width=700, height=500)
    else:
        st.error("Address not found. Try a more specific one.")
