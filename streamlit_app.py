import streamlit as st
from geopy.geocoders import Nominatim
import folium
from streamlit_folium import st_folium
import requests
import geopandas as gpd
from shapely.geometry import shape, Point
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

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
st.write("Enter an address and the tool will find the UK Power Networks primary that covers it and show the headroom availability.")

# Address input
address = st.text_input("📍 Enter Address")

if address:
    geolocator = Nominatim(user_agent="network_connection_checker")
    location = geolocator.geocode(address)

    if location:
        lat, lon = location.latitude, location.longitude
        st.success(f"Coordinates: Latitude {lat:.5f}, Longitude {lon:.5f}")

        m = folium.Map(location=[lat, lon], zoom_start=13, tiles="OpenStreetMap")
        folium.Marker([lat, lon], popup=address, icon=folium.Icon(color="lightgray")).add_to(m)

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
                    geometry = feature["fields"].get("geo_shape", feature["geometry"])
                    geojson_data["features"].append({
                        "type": "Feature",
                        "properties": feature["fields"],
                        "geometry": geometry
                    })

                gdf = gpd.GeoDataFrame.from_features(geojson_data["features"])
                point = Point(lon, lat)

                matching_rows = gdf[gdf.geometry.apply(lambda poly: poly.contains(point))]
                if not matching_rows.empty:
                    nearest_substation = matching_rows.iloc[0]

                    substation_name = nearest_substation['primary']
                    grid_site = nearest_substation.get('grid_site', 'N/A')
                    grid_supply_point = nearest_substation.get('grid_supply_point', 'N/A')
                    headroom = nearest_substation.get('demandrag', 'N/A')

                    substation_centroid = nearest_substation.geometry.centroid
                    sub_lat = substation_centroid.y
                    sub_lon = substation_centroid.x

                    st.write(f"🔌 **Containing Primary Substation**: {substation_name}")
                    st.write(f"⚡ **Grid Site**: {grid_site}")
                    st.write(f"🌍 **Grid Supply Point**: {grid_supply_point}")
                    st.write(f"💡 **Headroom (Available Capacity)**: {headroom}")

                    try:
                        transformer_url = (
                            "https://ukpowernetworks.opendatasoft.com/api/records/1.0/search/"
                            "?dataset=ukpn-primary-transformers"
                            f"&rows=1000"
                            f"&geofilter.distance={sub_lat},{sub_lon},1000"
                            f"&apikey={api_key}"
                        )
                        tr_response = requests.get(transformer_url, headers=headers)
                        tr_response.raise_for_status()
                        tr_data = tr_response.json()

                        if tr_data["nhits"] > 0:
                            st.subheader("🔧 Transformers at Substation")
                            for record in tr_data["records"]:
                                fields = record.get("fields", {})
                                name = fields.get("functionallocationname", "N/A")
                                rating = fields.get("onanrating_kva", "N/A")
                                voltage = fields.get("secondary_winding_voltage", "N/A")
                                related_primary = fields.get("sitedesc", "N/A")
                                st.markdown(f"**Transformer**: {name} - {related_primary}| **Rating**: {rating} MVA | **Voltage**: {voltage} kV")
                        else:
                            st.info("No transformer data found at this location.")
                    except Exception as e:
                        st.error(f"Error loading transformer data: {e}")

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
                        [sub_lat, sub_lon],
                        popup=f"{substation_name}: {grid_supply_point}",
                        icon=folium.Icon(color="red")
                    ).add_to(m)

                    st_folium(m, width=700, height=500)

                    try:
                        demand_api = (
                            "https://ukpowernetworks.opendatasoft.com/api/records/1.0/search/"
                            "?dataset=ukpn-primary-transformer-power-flow-historic-half-hourly-epn"
                            f"&rows=10000"
                            f"&q=tx_id:watsons_rd_primary_11kv_t1"
                            f"&sort=-timestamp"
                            f"&apikey={api_key}"
                        )

                        response = requests.get(demand_api, headers=headers)
                        response.raise_for_status()
                        demand_data = response.json()

                        if demand_data["nhits"] > 0:
                            records = demand_data["records"]
                            df = pd.DataFrame([{
                                'timestamp': rec['fields']['timestamp'],
                                'current_amps': rec['fields']['current_amps']
                            } for rec in records if 'timestamp' in rec['fields'] and 'current_amps' in rec['fields']])

                            df['timestamp'] = pd.to_datetime(df['timestamp'])
                            df = df.set_index('timestamp').sort_index()

                            df['time'] = df.index.time
                            profile = df.groupby('time')['current_amps'].mean().reset_index()

                            fig = px.line(profile, x='time', y='current_amps', title="📊 Avg. Half-Hourly Demand Profile",
                                          labels={'time': 'Time of Day', 'current_amps': 'Current (A)'})
                            fig = px.line(
                                profile,
                                x='time',
                                y='current_amps',
                                title="📊 Avg. Half-Hourly Demand Profile",
                                labels={'time': 'Time of Day', 'current_amps': 'Current (A)'}
                            )

                            # Update layout for futuristic theme
                            fig.update_layout(
                                plot_bgcolor='#1a1a1a',
                                paper_bgcolor='#1a1a1a',
                                font=dict(color='#00ffc3', family='Arial'),
                                title_font=dict(size=20, color='#00ffc3'),
                                xaxis=dict(
                                    title='Time of Day',
                                    showgrid=True,
                                    gridcolor='#444',
                                    tickfont=dict(color='#ffffff'),
                                    title_font=dict(color='#00ffc3')
                                ),
                                yaxis=dict(
                                    title='Current (A)',
                                    showgrid=True,
                                    gridcolor='#444',
                                    tickfont=dict(color='#ffffff'),
                                    title_font=dict(color='#00ffc3')
                                ),
                                hoverlabel=dict(
                                    bgcolor="#333",
                                    font_size=12,
                                    font_family="Arial"
                                ),
                            )

                            # Update line style
                            fig.update_traces(line=dict(color='#00ffc3', width=3))

                            
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.info("No half-hourly demand data found for this substation.")
                    except Exception as e:
                        st.error(f"Error loading demand data: {e}")

                else:
                    st.warning("No substation coverage found at the specified location.")
            else:
                st.warning("No records found in the vicinity. Please try a different address or expand the search radius.")
        except Exception as e:
            st.error(f"Could not load UK Power Networks data: {e}")
    else:
        st.error("Address not found. Try a more specific one.")
