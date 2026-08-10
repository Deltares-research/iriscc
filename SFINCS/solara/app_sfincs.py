# SFINCS Solara app (standalone, `solara run`-compatible)
#
# Key difference vs. the notebook version:
#   ipywidgets / ipyleaflet objects (the Map and all LayerGroups) are created
#   PER SESSION inside `init_widgets()`, which runs from `Page` via
#   `solara.use_memo(..., [])`. Creating them at import time causes
#   `solara run` to close them during startup, which produced the
#   "Widget <LayerGroup> has been closed" RuntimeError.
#
# Run with:
#   pixi run solara run SFINCS/solara/app_sfincs.py --host=0.0.0.0 --port=8765 \
#       --root-path=/user/<name>/proxy/8765
#
# NOTE: the hydromt model objects (sf, ds_basins, ...) and most widget-holding
# reactives are module-level globals. This is fine for a single user, but is
# shared across sessions if multiple people open the app at once.

import solara
from ipyleaflet import (
    Map,
    basemaps,
    GeoJSON,
    Rectangle,
    LayerGroup,
    CircleMarker,
    WidgetControl,
    Polyline,
    AwesomeIcon,
    Marker,
    Icon,
)
import ipywidgets as widgets
from shapely.geometry import Point

import datetime
import numpy as np
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.cm as cm
import matplotlib.colors as colors
from matplotlib.colors import ListedColormap, TwoSlopeNorm
from branca.colormap import LinearColormap
from pyogrio import set_gdal_config_options
import json

import hydromt
from hydromt_sfincs import SfincsModel
from hydromt_sfincs.workflows import river_source_points
from pathlib import Path

import cartopy.crs as ccrs
from pyproj import Transformer
import pandas as pd

import io
import contextlib
import os
import threading

from IPython.display import display

proj = ccrs.PlateCarree()  # plot projection

# ---------------------------------------------------------------------------
# Widget-holding globals: created lazily in init_widgets() (NOT at import time)
# ---------------------------------------------------------------------------
m = None  # ipyleaflet.Map, created per session
tab_layers = {}  # dict[str, LayerGroup], created per session

current_layer_group = solara.reactive(None)
tab_controls = solara.reactive({})
control_update_signal = solara.reactive(0)
current_control = solara.reactive(None)
rectangle = solara.reactive(None)

control_signals = {
    "Config": solara.reactive(0),
    "ModDom": solara.reactive(0),
    "GridGen": solara.reactive(0),
    "Elev": solara.reactive(0),
    "ActC": solara.reactive(0),
    "wlBnd": solara.reactive(0),
    "rInflP": solara.reactive(0),
    "LRoughInf": solara.reactive(0),
    "subgrid": solara.reactive(0),
    "obs": solara.reactive(0),
    "forcing": solara.reactive(0),
    "model": solara.reactive(0),
}

configdone = solara.reactive(False)
modeldomaindone = solara.reactive(False)
elevationdone = solara.reactive(False)
activecellsdone = solara.reactive(False)
waterlevelbnddone = solara.reactive(False)
riverinflowdone = solara.reactive(False)
roughnesssubgriddone = solara.reactive(False)
obsdone = solara.reactive(False)
forcingdone = solara.reactive(False)

_TAB_KEYS = [
    "Config",
    "ModDom",
    "GridGen",
    "Elev",
    "ActC",
    "wlBnd",
    "rInflP",
    "LRoughInf",
    "subgrid",
    "obs",
    "forcing",
    "model",
]


def init_widgets():
    """Create the map and layer groups once, after import (per component session)."""
    global m, tab_layers
    if m is None:
        m = Map(
            center=(53.5, -0.5),
            zoom=8,
            scroll_wheel_zoom=True,
            basemap=basemaps.OpenStreetMap.Mapnik,
        )
        tab_layers = {k: LayerGroup() for k in _TAB_KEYS}
        current_layer_group.set(tab_layers["Config"])
        m.on_interaction(handle_map_click)
    return m


# ===========================================================================
# 1) Configuration
# ===========================================================================
continuous_update = solara.reactive(True)

sf_logger_name = solara.reactive("SFINCS_log")

model_path = solara.reactive("/home/jovyan/")  # ("C:\\") # HIER PATH ÄNDERN
sf_root = model_path  # HERE THE SAME, DELETED v1 FOLDER
model_name = solara.reactive(model_path.value.split("/")[-1])  # get model_name from model_path

# modelbuilder domain geojson
data_catalog_fn = solara.reactive("/home/jovyan/")

# modelbuilder domain geojson
region_fn = solara.reactive("/home/jovyan/")  # ("C:\\") # HIER PATH ÄNDERN

init_tools_status = solara.reactive("Idle")


def init_tools():
    global data_catalog, sf
    init_tools_status.set("Plotting")
    # sf_logger = setuplog(sf_logger_name.value,log_level=10)
    #try:
    # Use line below for own data_catalog file
    # data_catalog = hydromt.DataCatalog(data_catalog_fn)
    data_catalog = hydromt.DataCatalog(data_catalog_fn.value)
    sf = SfincsModel(data_libs=data_catalog_fn.value, root=sf_root.value, mode="w+")
    #except:
    #    # Use line below for 'deltares_data' data_catalog file
    #    data_catalog = hydromt.DataCatalog(data_libs=["deltares_data"])
    #    sf = SfincsModel(data_libs=["deltares_data"], root=sf_root.value, mode="w+")
    
    init_tools_status.set("Done")

    configdone.set(True)


def set_environ(dict_name):
    os.environ.pop("AWS_NO_SIGN_REQUEST", None)
    os.environ.pop("AWS_ACCESS_KEY_ID", None)
    os.environ.pop("AWS_SECRET_ACCESS_KEY", None)
    os.environ.pop("AWS_S3_ENDPOINT", None)
    os.environ.pop("AWS_VIRTUAL_HOSTING", None)
    os.environ.pop("AWS_HTTPS", None)
    os.environ.pop("AWS_DEFAULT_REGION", None)
    if "public" in data_dict[dict_name]:
        opts = opts_public
    elif "destine" in data_dict[dict_name]:
        opts = opts_destine
    else:
        opts = opts_deltares

    for k, v in opts.items():
        os.environ[k] = v
    set_gdal_config_options(opts)
    

data_dict = {
    "topo": "merit_hydro",
    "bathy": "gebco",
    "infiltration": "gcn250",
    "lulc": "globcover",
    "basins": "hydro_basin_atlas_level12",
    "hydrography": "merit_hydro",
    "precip": "era5_hourly_destine",
}

opts_deltares = {
    "AWS_ACCESS_KEY_ID": "J3lh3qbnU916sOWqJoQR",
    "AWS_SECRET_ACCESS_KEY": "EZU4YW3YJPfRpMiAdLrwWg6yTC96gqCcs6HSppsr",
    "AWS_S3_ENDPOINT": "s3.deltares.nl",
    "AWS_VIRTUAL_HOSTING": "FALSE",
    "AWS_HTTPS": "YES",
    "AWS_DEFAULT_REGION": "eu-west-1",
}

opts_destine = {
    "AWS_DEFAULT_REGION": "eu-west-1",
}

opts_public = {
    "AWS_NO_SIGN_REQUEST": "YES",
    "AWS_DEFAULT_REGION": "eu-west-1",
}

@solara.component
def Tab_Configuration():
    with solara.Card("Configuration", style={"width": "100%", "padding": "12px"}):
        solara.Markdown("**Select Model:**")
        solara.InputText("Model directory", value=model_path, continuous_update=True)
        solara.Text(f"Model Name: {model_name.value}")
        # solara.InputText("Model Name (avoid spaces)", value=model_name, continuous_update=continuous_update.value)
        path_model = Path(model_path.value)
        if model_path.value:
            if not path_model.exists():
                solara.Error("Path does not exist.")

        solara.Markdown("**Select data catalog file (optional):**")
        solara.InputText("Select .yml-file", value=data_catalog_fn, continuous_update=True)
        path_yml = Path(data_catalog_fn.value)
        if data_catalog_fn.value:
            if not data_catalog_fn.value.endswith(".yml"):
                solara.Error(
                    label='Error: File must end with ".yml"',
                    text=False,
                    dense=True,
                    outlined=True,
                    icon=False,
                )
            elif not path_yml.exists():
                solara.Error("File does not exist.")
        
        solara.Markdown("**Select modelbuilder domain:**")
        solara.InputText("Select .geojson-file", value=region_fn, continuous_update=True)
        path_geojson = Path(region_fn.value)
        if region_fn.value:
            if not region_fn.value.endswith(".geojson"):
                solara.Error(
                    label='Error: File must end with ".geojson"',
                    text=False,
                    dense=True,
                    outlined=True,
                    icon=False,
                )
            elif not path_geojson.exists():
                solara.Error("File does not exist.")

        solara.Button(label="Initialise Tools", on_click=init_tools, continuous_update=True)

        if init_tools_status.value == "Plotting":
            solara.Markdown("Initialising Tools... Please wait.")
        elif init_tools_status.value == "Done":
            solara.Markdown("**Done!**")

    with solara.Row(justify="end"):
        solara.Button(
            label="Go to Step 2.",
            on_click=lambda: selected_tab.set("ModDom"),
            disabled=not configdone.value,
        )

# Tab_Configuration()
# ===========================================================================
# 2) Model Domain (including Grid Generation)
# ===========================================================================
setup_domain_status = solara.reactive("Idle")
ref_date = solara.reactive(datetime.date(2013, 12, 1))
date_min = solara.reactive(datetime.date(2013, 12, 1))
date_max = solara.reactive(datetime.date(2013, 12, 14))


def set_up_domain():
    global SW, NE, rectangle, ds_basins, sf
    setup_domain_status.set("Plotting")

    region = gpd.read_file(region_fn.value)

    sf.config.update(  # UPDATE # sf.setup_config(
        **{
            "tref": ref_date.value.strftime("%Y%m%d 000000"),
            "tstart": date_min.value.strftime("%Y%m%d 000000"),
            "tstop": date_max.value.strftime("%Y%m%d 000000"),
        }
    )
    
    set_environ("basins")
    ds_basins = data_catalog.get_geodataframe(data_dict["basins"], geom=region)
    geo_json_data = json.loads(ds_basins.to_json())
    geo_json_layer = GeoJSON(data=geo_json_data)

    SW = (
        ds_basins["geometry"].total_bounds[[0, 2, 1, 3]][2],
        ds_basins["geometry"].total_bounds[[0, 2, 1, 3]][0],
    )
    NE = (
        ds_basins["geometry"].total_bounds[[0, 2, 1, 3]][3],
        ds_basins["geometry"].total_bounds[[0, 2, 1, 3]][1],
    )

    rectangle.value = Rectangle(bounds=(SW, NE), color="white", fill_opacity=0)  # , weight=1)

    if rectangle.value in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(rectangle.value)
    current_layer_group.value.add_layer(rectangle.value)

    if geo_json_layer in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(geo_json_layer)
    current_layer_group.value.add_layer(geo_json_layer)

    sf.grid.create_from_region(  # UPDATE # sf.setup_grid_from_region()
        region={"bbox": ds_basins["geometry"].total_bounds},
        res=200,
        rotated=False,
        crs="utm",
    )
    
    # Convert resulting grid lines to GeoDataFrame
    grid_lines = sf.grid.to_gdf()
    grid_json = json.loads(grid_lines.to_json())
    
    # Add as GeoJSON layer to Solara map
    grid_layer = GeoJSON(data=grid_json, style={"color": "blue", "weight": 1}, name="Grid")
    
    if grid_layer in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(grid_layer)
    current_layer_group.value.add_layer(grid_layer)

    setup_domain_status.set("Done")

    modeldomaindone.set(True)

@solara.component
def Tab_Model_Domain():
    solara.Markdown("Date selection:", style={"color": "inherit"})
    solara.Text("Reference date:")
    solara.lab.InputDate(ref_date)
    solara.Text("Select start date:")
    solara.lab.InputDate(date_min)
    solara.Text("Select stop date:")
    solara.lab.InputDate(date_max)
    if date_max.value < date_min.value:
        solara.Markdown(
            "**Warning**: The end date cannot be earlier than the start date.",
            style={"color": "red", "color": "inherit"},
        )

    # solara.use_effect(update_rectangle)#, dependencies=[lat_min.value, lat_max.value, lon_min.value, lon_max.value]) # RESET THE RECTANGLE: Model area
    solara.Button(label="set-up domain", on_click=set_up_domain, continuous_update=True)
    if setup_domain_status.value == "Plotting":
        solara.Markdown("Set-up model domain... Please wait.", style={"color": "inherit"})
    elif setup_domain_status.value == "Done":
        solara.Markdown("**Done!**", style={"color": "inherit"})

    with solara.Row(justify="end"):
        solara.Button(
            label="Go to Step 3.",
            on_click=lambda: selected_tab.set("Elev"),
            disabled=not modeldomaindone.value,
        )

# Tab_Model_Domain()

# ===========================================================================
# 4) Elevation
# ===========================================================================
step_elev = solara.reactive(7)
elev_layer = solara.reactive(LayerGroup())

elev_plot_done = solara.reactive(False)

plot_elev_status = solara.reactive("Idle")


def plot_elev():
    global scatter_layer_g, legend_elev  # , elev_layer
    plot_elev_status.set("Plotting")
    bounds_array = np.array(ds_basins.total_bounds, dtype=float)
    bbox = tuple(bounds_array.tolist())
    # f = sf.data_catalog.get_rasterdataset("fabdem", bbox=bbox) # topography # PROBLEM: min = -9999
    set_environ("bathy")
    g = sf.data_catalog.get_rasterdataset(data_dict["bathy"], bbox=bbox)  # bathymetry

    terrain = plt.get_cmap("terrain", 256) # updated from terrain = cm.get_cmap("terrain", 256)
    terrain_colors = terrain(np.linspace(0, 1, 256))
    land_part = terrain_colors[
        70:
    ]  ########### -----------------------------------------> ggf anheben!!!
    land_rescaled = land_part[np.linspace(0, len(land_part) - 1, 128, dtype=int)]

    mid_blue = np.array([70, 161, 230]) / 255  # steelblue
    dark_blue = np.array([41, 50, 141]) / 255  # navy
    blue_rgb = np.linspace(dark_blue, mid_blue, 128)
    blue_rescaled = np.hstack([blue_rgb, np.ones((128, 1))])

    combined_colors = np.vstack([blue_rescaled, land_rescaled])
    combined = ListedColormap(combined_colors)

    vmin = np.nanmin(g.values)
    vmax = min(np.nanmax(g.values), 200)  # print("Min:", vmin, "Max:", vmax)
    norm = TwoSlopeNorm(vmin=vmin, vcenter=0, vmax=vmax)

    scatter_layer_g = LayerGroup()

    # step_elev = 7 # mit 50: 15 dots, mit 100: 8 dots
    for i in range(0, g.values.shape[0], step_elev.value):
        for j in range(0, g.values.shape[1], step_elev.value):
            val = g.values[i, j]
            if np.isnan(val):
                continue
            color = colors.to_hex(combined(norm(val)))
            marker = CircleMarker(
                location=(g.y.values[i], g.x.values[j]),
                radius=3,
                color=color,
                fill_color=color,
                fill_opacity=0.6,
            )
            scatter_layer_g.add_layer(marker)

    # LEGEND ##############
    blue_colors = combined_colors[:128]
    land_colors = combined_colors[128:]

    def rounded_g(gmin=np.nanmin(g.values)):
        if gmin <= 500:
            return round(gmin / 50) * 50
        else:
            return round(gmin / 100) * 100

    vmin = rounded_g()  # -50 # np.nanmin(g.values)
    vmax = min(np.nanmax(g), 200)  # fz
    midpoint = 0
    blue_vals = np.linspace(vmin, midpoint, len(blue_colors), endpoint=False)
    land_vals = np.linspace(midpoint, vmax, len(land_colors))
    all_vals = np.concatenate([blue_vals, land_vals])
    all_colors = np.vstack([blue_colors, land_colors])
    all_colors_hex = [colors.to_hex(c) for c in all_colors]

    legend_elev = LinearColormap(
        colors=all_colors_hex,
        index=all_vals,
        vmin=vmin,
        vmax=vmax,
        caption="Elevation (m)",
    )

    # ADD TO MAP ################################################################
    # if scatter_layer_g in current_layer_group.value.layers:
    #     current_layer_group.value.remove_layer(scatter_layer_g)
    # current_layer_group.value.add_layer(scatter_layer_g)
    if elev_layer.value in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(elev_layer.value)
    elev_layer.set(scatter_layer_g)
    current_layer_group.value.add_layer(
        elev_layer.value
    )  # vorher erfolgreich, aber nicht zu resetten: current_layer_group.value.add_layer(scatter_layer_g)

    legend_html = widgets.HTML(value=legend_elev._repr_html_())
    legend_control = WidgetControl(widget=legend_html, position="bottomright")
    tab_controls.value["Elev"] = legend_control  # m.add_control(legend_control)
    # control_update_signal.set(control_update_signal.value + 1)
    control_signals["Elev"].set(control_signals["Elev"].value + 1)

    plot_elev_status.set("Done")
    elev_plot_done.set(True)
    elevationdone.set(True)


def reset_elev():
    if elev_layer.value in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(elev_layer.value)

    if "Elev" in tab_controls.value:
        legend_control = tab_controls.value["Elev"]
        if legend_control in m.controls:
            m.remove_control(legend_control)
        tab_controls.value["Elev"] = None

    # Reset status or signals if needed
    control_signals["Elev"].set(control_signals["Elev"].value + 1)
    plot_elev_status.set("")
    elev_plot_done.set(False)
    step_elev.set(7)

@solara.component
def Tab_Elevation():
    solara.Markdown(
        "**Setting step size for elevation plot:** Reducing the step size increases computational load and may significantly extend execution time.",
        style={"color": "inherit"},
    )
    solara.SliderInt("Step Size", value=step_elev, min=-1, max=50)
    solara.Markdown(f"**Int value**: {step_elev.value}", style={"color": "inherit"})
    # with solara.Row():
    # solara.Button("Reset", on_click=lambda: step_elev.set(7))

    solara.Button(label="Plot elevation", on_click=plot_elev, continuous_update=True)
    if plot_elev_status.value == "Plotting":
        solara.Markdown(
            "Preparing elevation data... Please wait. This might take a couple of minutes.",
            style={"color": "inherit"},
        )
    elif plot_elev_status.value == "Done":
        solara.Markdown("**Done!**", style={"color": "inherit"})
    else:
        solara.Markdown("")

    solara.Button("Reset", on_click=reset_elev, disabled=not elev_plot_done.value)
    # if not elev_plot_done.value:
    #     solara.Markdown("Plot elevation first.")

    with solara.Row(justify="end"):
        solara.Button(
            label="Go to Step 4.",
            on_click=lambda: selected_tab.set("ActC"),
            disabled=not elevationdone.value,
        )

# Tab_Elevation()

# ===========================================================================
# 5) Active Cells
# ===========================================================================
step_actc = solara.reactive(7)
actc_layer = solara.reactive(LayerGroup())
actc_plot_done = solara.reactive(False)
plot_actc_status = solara.reactive("Idle")


def plot_actc():
    global mask_active, msk, datasets_dep
    plot_actc_status.set("Plotting")
    
    ## done in tab grid generation
    #sf.grid.create_from_region(  # UPDATE # sf.setup_grid_from_region()
    #    region={"bbox": ds_basins["geometry"].total_bounds},
    #    res=200,
    #    rotated=False,
    #    crs="utm",
    #)
    
    datasets_dep = [{"elevation": data_dict["topo"], "zmin": 0.001}, {"elevation": data_dict["bathy"]}]
    
    set_environ("topo")
    # set_environ("bathy") # Currently 'topo' and 'bathy' should come from the same type of sources location (public/password-protected)
    _ = sf.elevation.create(elevation_list=datasets_dep, buffer_cells=1)  # UPDATE # _ = sf.setup_dep(datasets_dep=datasets_dep)

    # create mask
    mask_active = gpd.GeoDataFrame(geometry=ds_basins["geometry"])
    sf.mask.create_active(
        zmax=0, zmin=-30, include_polygon=mask_active, reset_mask=True, fill_area=99999, drop_area=10,
    )
    # UPDATE # sf.setup_mask_active(zmax=0, zmin=-30, include_mask=mask_active, reset_mask=True)
    # UPDATE # sf.setup_mask_active(fill_area=10, reset_mask=False)
    # UPDATE # sf.setup_mask_active(drop_area=10, reset_mask=False)
    msk = sf.grid.mask  # np.unique(msk.values) # print(np.count_nonzero(msk.values == 1)) # print(np.count_nonzero(msk.values == 0))

    # Transform locations from [m] to lat/lon
    transformer = Transformer.from_crs(msk.rio.crs, "EPSG:4326", always_xy=True)
    X, Y = np.meshgrid(msk.x.values, msk.y.values)
    lon, lat = transformer.transform(X, Y)

    # create scatter plot
    # # step_actc.value = 10 ######################## SET BY USER!
    # scatter_layer_m = LayerGroup()
    # for i in range(0, msk.values.shape[0], step_actc.value):
    #     for j in range(0, msk.values.shape[1], step_actc.value):
    #         val = msk.values[i, j]
    #         if np.isnan(val) or val == 0:
    #             continue
    #         if val == 1:
    #             color = "#666666"  # grey
    #         elif val == 2:
    #             color = "#e41a1c"  # red
    #         elif val == 3:
    #             color = "#984ea3"  # purple
    #         marker = CircleMarker(
    #             location=(lat[i, j], lon[i, j]),
    #             radius=2,
    #             color=color,
    #             fill_color=color,
    #             fill_opacity=0.4
    #         )
    #         scatter_layer_m.add_layer(marker)

    scatter_layer_m = LayerGroup()
    # First pass: plot grey dots with step
    for i in range(msk.shape[0]):
        for j in range(msk.shape[1]):
            val = msk.values[i, j]
            if val == 1 and i % step_actc.value == 0 and j % step_actc.value == 0:
                marker = CircleMarker(
                    location=(lat[i, j], lon[i, j]),
                    radius=2,
                    color="#666666",  # grey
                    fill_color="#666666",
                    fill_opacity=0.4,
                )
                scatter_layer_m.add_layer(marker)
    # Second pass: plot red and purple dots at full resolution
    for i in range(msk.shape[0]):
        for j in range(msk.shape[1]):
            val = msk.values[i, j]
            if val == 2:
                color = "#e41a1c"  # red
            elif val == 3:
                color = "#984ea3"  # purple
            else:
                continue
            marker = CircleMarker(
                location=(lat[i, j], lon[i, j]),
                radius=2,
                color=color,
                fill_color=color,
                fill_opacity=0.8,  # slightly more opaque to stand out
            )
            scatter_layer_m.add_layer(marker)

    # ADD TO MAP ################################################################
    if actc_layer.value in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(actc_layer.value)
    actc_layer.set(scatter_layer_m)
    current_layer_group.value.add_layer(
        actc_layer.value
    )  # vorher erfolgreich, aber nicht zu resetten: current_layer_group.value.add_layer(scatter_layer_m)

    # Legend
    legend_html = widgets.HTML(
        value="""
    <div style="padding:5px; background:white; border-radius:5px; font-size:14px; color:black;">
        <b>msk</b><br>
        <div style="margin:2px;"><span style="display:inline-block;width:12px;height:12px;background:#666666;margin-right:5px;"></span> 1</div>
        <div style="margin:2px;"><span style="display:inline-block;width:12px;height:12px;background:#e41a1c;margin-right:5px;"></span> 2</div>
        <div style="margin:2px;"><span style="display:inline-block;width:12px;height:12px;background:#984ea3;margin-right:5px;"></span> 3</div>
    </div>
    """
    )
    legend_control = WidgetControl(widget=legend_html, position="bottomright")
    tab_controls.value["ActC"] = legend_control  # m.add_control(legend_control)
    # control_update_signal.set(control_update_signal.value + 1)
    control_signals["ActC"].set(control_signals["ActC"].value + 1)

    plot_actc_status.set("Done")
    actc_plot_done.set(True)
    activecellsdone.set(True)


def reset_actc():
    if actc_layer.value in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(actc_layer.value)

    if "ActC" in tab_controls.value:
        legend_control = tab_controls.value["ActC"]
        if legend_control in m.controls:
            m.remove_control(legend_control)
        tab_controls.value["ActC"] = None

    # Reset status or signals if needed
    control_signals["ActC"].set(control_signals["ActC"].value + 1)
    plot_actc_status.set("")
    actc_plot_done.set(False)
    step_actc.set(7)

@solara.component
def Tab_Active_Cells():
    solara.Markdown(
        "**Setting step size for plotting active cells:** Reducing the step size increases computational load and may significantly extend execution time.",
        style={"color": "inherit"},
    )
    solara.SliderInt("Step Size", value=step_actc, min=-1, max=50)
    solara.Markdown(f"**Int value**: {step_actc.value}", style={"color": "inherit"})

    solara.Button(label="Plot active cells", on_click=plot_actc, continuous_update=True)
    if plot_actc_status.value == "Plotting":
        solara.Markdown(
            "Preparing active cells data... Please wait. This might take a couple of minutes.",
            style={"color": "inherit"},
        )
    elif plot_actc_status.value == "Done":
        solara.Markdown("**Done!**", style={"color": "inherit"})
    else:
        solara.Markdown("")

    # with solara.Row():
    solara.Button("Reset", on_click=reset_actc, disabled=not actc_plot_done.value)
    # if not actc_plot_done.value:
    #     solara.Markdown("Plot active cells first.")

    with solara.Row(justify="end"):
        solara.Button(
            label="Go to Step 5.",
            on_click=lambda: selected_tab.set("wlBnd"),
            disabled=not activecellsdone.value,
        )


# Tab_Active_Cells()

# ===========================================================================
# 6) Waterlevel bound
# ===========================================================================
step_wlbnd = solara.reactive(7)
wlbnd_layer = solara.reactive(LayerGroup())
wlbnd_plot_done = solara.reactive(False)
plot_wlbnd_status = solara.reactive("Idle")


def plot_wlbnd():
    global waterlevel_bnd
    plot_wlbnd_status.set("Plotting")

    # if mask_active does not exist:
    try:
        mask_active
    except NameError:
        mask_active = gpd.GeoDataFrame(geometry=ds_basins["geometry"])

    excl_bounds = gpd.GeoDataFrame(geometry=mask_active.to_crs(sf.crs).buffer(1000))
    sf.mask.create_boundary(
        btype="waterlevel",
        include_zmax=-5,
        reset_bounds=True,
        exclude_polygon=excl_bounds,
    )  # UPDATE # sf.setup_mask_bounds(btype='waterlevel', zmax=-5, reset_bounds=True, exclude_mask=excl_bounds)  # connectivity=4)
    excl_bounds_wgs84 = excl_bounds.to_crs(epsg=4326)
    geo_json_data = excl_bounds_wgs84.__geo_interface__

    try:
        msk
    except NameError:
        msk = sf.grid.mask

    mask_array = sf.grid.mask
    X, Y = np.meshgrid(mask_array.x.values, mask_array.y.values)
    transformer = Transformer.from_crs(msk.rio.crs, "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(X, Y)

    # step_wlbnd.value = 10 ###################### set by user
    scatter_layer_wlb = LayerGroup()
    # First pass: plot grey dots with step
    for i in range(mask_array.shape[0]):
        for j in range(mask_array.shape[1]):
            val = mask_array.values[i, j]
            if val == 1 and i % step_wlbnd.value == 0 and j % step_wlbnd.value == 0:
                marker = CircleMarker(
                    location=(lat[i, j], lon[i, j]),
                    radius=2,
                    color="#666666",  # grey
                    fill_color="#666666",
                    fill_opacity=0.4,
                )
                scatter_layer_wlb.add_layer(marker)
    # Second pass: plot red and purple dots at full resolution
    waterlevel_bnd = []  # needed later for 7) River Inflow Points plot
    for i in range(mask_array.shape[0]):
        for j in range(mask_array.shape[1]):
            val = mask_array.values[i, j]
            if val == 2:
                color = "#e41a1c"  # red
            elif val == 3:
                color = "#984ea3"  # purple
            else:
                continue

            marker = CircleMarker(
                location=(lat[i, j], lon[i, j]),
                radius=2,
                color=color,
                fill_color=color,
                fill_opacity=0.8,  # slightly more opaque to stand out
            )
            scatter_layer_wlb.add_layer(marker)

            if val == 2:
                waterlevel_bnd.append(
                    marker
                )  # needed later for 7) River Inflow Points plot

    ########################################################################################################################

    # ADD TO MAP ################################################################
    if wlbnd_layer.value in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(wlbnd_layer.value)
    wlbnd_layer.set(scatter_layer_wlb)
    current_layer_group.value.add_layer(
        wlbnd_layer.value
    )  # vorher erfolgreich, aber nicht zu resetten: current_layer_group.value.add_layer(scatter_layer_wlb)

    # Legend
    legend_html = widgets.HTML(
        value="""
    <div style="padding:5px; background:white; border-radius:5px; font-size:14px; color:black;">
        <b>msk</b><br>
        <div style="margin:2px;"><span style="display:inline-block;width:12px;height:12px;background:#666666;margin-right:5px;"></span> 1</div>
        <div style="margin:2px;"><span style="display:inline-block;width:12px;height:12px;background:#e41a1c;margin-right:5px;"></span> 2</div>
        <div style="margin:2px;"><span style="display:inline-block;width:12px;height:12px;background:#984ea3;margin-right:5px;"></span> 3</div>
    </div>
    """
    )
    legend_control = WidgetControl(widget=legend_html, position="bottomright")
    tab_controls.value["wlBnd"] = legend_control  # m.add_control(legend_control)
    # control_update_signal.set(control_update_signal.value + 1)
    control_signals["wlBnd"].set(control_signals["wlBnd"].value + 1)

    plot_wlbnd_status.set("Done")
    wlbnd_plot_done.set(True)
    waterlevelbnddone.set(True)


def reset_wlbnd():
    if wlbnd_layer.value in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(wlbnd_layer.value)

    if "wlBnd" in tab_controls.value:
        legend_control = tab_controls.value["wlBnd"]
        if legend_control in m.controls:
            m.remove_control(legend_control)
        tab_controls.value["wlBnd"] = None

    # Reset status or signals if needed
    control_signals["wlBnd"].set(control_signals["wlBnd"].value + 1)
    plot_wlbnd_status.set("")
    wlbnd_plot_done.set(False)
    step_wlbnd.set(7)

@solara.component
def Tab_Waterlevel_Bound():
    solara.Markdown(
        "**Setting step size for plotting waterlevel bound:** Reducing the step size increases computational load and may significantly extend execution time.",
        style={"color": "inherit"},
    )
    solara.SliderInt("Step Size", value=step_wlbnd, min=-1, max=50)
    solara.Markdown(f"**Int value**: {step_wlbnd.value}", style={"color": "inherit"})

    solara.Button(label="Plot waterlevel bound", on_click=plot_wlbnd, continuous_update=True)
    if plot_wlbnd_status.value == "Plotting":
        solara.Markdown(
            "Preparing waterlevel bound data... Please wait. This might take a couple of minutes.",
            style={"color": "inherit"},
        )
    elif plot_wlbnd_status.value == "Done":
        solara.Markdown("**Done!**", style={"color": "inherit"})
    else:
        solara.Markdown("")

    # with solara.Row():
    solara.Button("Reset", on_click=reset_wlbnd, disabled=not wlbnd_plot_done.value)
    # if not wlbnd_plot_done.value:
    #     solara.Markdown("Plot waterlevel bound first.")

    with solara.Row(justify="end"):
        solara.Button(
            label="Go to Step 6.",
            on_click=lambda: selected_tab.set("rInflP"),
            disabled=not waterlevelbnddone.value,
        )

# Tab_Waterlevel_Bound()

# ===========================================================================
# 7) River Inflow Points
# ===========================================================================
plot_rInflP_status = solara.reactive("Idle")
rInflP_layer = solara.reactive(LayerGroup())
rinflp_plot_done = solara.reactive(False)


def plot_rInflP():
    plot_rInflP_status.set("Plotting")
    global src_river_layer, riverinflow_layers

    # REMOVE existing layers if present
    if rInflP_layer.value in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(rInflP_layer.value)
    if scatter_layer_g in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(scatter_layer_g)

    # Add Elevation Layer
    # rInflP_layer.set(scatter_layer_g)
    # current_layer_group.value.add_layer(rInflP_layer.value)
    # vorher erfolgreich(er), aber nicht zu resetten:
    current_layer_group.value.add_layer(scatter_layer_g)

    combined_layer = LayerGroup()
    src_river_layer = LayerGroup()

    # Add RIVERS
    set_environ("hydrography")
    sf.rivers.create_river_inflow(  # UPDATE # sf.setup_river_inflow(
        hydrography=data_dict["hydrography"],
        river_len=1000,
        river_upa=10,
        keep_rivers_geom=True,
    )

    rivers_inflow = sf.rivers.data # UPDATE # rivers_inflow = sf.geoms["rivers_inflow"]
    transformer = Transformer.from_crs(rivers_inflow.crs, "EPSG:4326", always_xy=True)

    for geom in rivers_inflow["geometry"]:
        if geom.geom_type == "LineString":
            x, y = geom.xy
            lon, lat = transformer.transform(x, y)
            locations = list(zip(lat, lon))
            polyline = Polyline(locations=locations, color="blue", weight=2, fill=False)
            combined_layer.add_layer(polyline)
            src_river_layer.add_layer(polyline)

    # Add SOURCE POINTS
    gdf_pnt = river_source_points(
        gdf_riv=rivers_inflow, gdf_mask=mask_active, src_type="inflow"
    )
    gdf_pnt = gdf_pnt.to_crs(rivers_inflow.crs)
    transformer = Transformer.from_crs(gdf_pnt.crs, "EPSG:4326", always_xy=True)

    text_step = 0.035
    label_markers = []

    for idx, geom in enumerate(gdf_pnt.geometry):
        if geom.geom_type == "Point":
            lon, lat = transformer.transform(geom.x, geom.y)
            marker = CircleMarker(
                location=(lat, lon),
                radius=5,
                color="black",
                weight=1,
                fill=True,
                fill_color="white",
                fill_opacity=1.0,
            )
            combined_layer.add_layer(marker)
            src_river_layer.add_layer(marker)

            ###################################################### THIS PART!!! ######################################################
            label = Marker(
                location=(lat + text_step, lon),  # Slight offset to avoid overlap
                icon=Icon(
                    icon_url="data:image/svg+xml;charset=utf-8,"
                    + f"<svg xmlns='http://www.w3.org/2000/svg' width='30' height='20'><text x='0' y='15' font-size='20' font-weight='bold' fill='black'>{idx + 1}</text></svg>",
                    icon_size=[30, 20],
                ),
            )
            # mmm.add_layer(label)
            combined_layer.add_layer(label)
            src_river_layer.add_layer(label)
            label_markers.append((label, lat, lon))

    def update_text_step(change):
        global text_step
        zoom = change["new"]
        if zoom <= 7:
            text_step = 0.035
        elif zoom == 8:
            text_step = 0.025
        elif zoom == 9:
            text_step = 0.015
        elif zoom == 10:
            text_step = 0.01
        else:
            text_step = 0.01 * (0.5 ** (zoom - 10))

        for label, lat, lon in label_markers:
            label.location = (lat + text_step, lon)

    m.observe(update_text_step, names="zoom")

    ############################################################################################################

    # Add WATERLEVEL BOUND markers
    for marker in waterlevel_bnd:
        combined_layer.add_layer(marker)

    # Update layer on map
    if rInflP_layer.value in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(rInflP_layer.value)
    rInflP_layer.set(combined_layer)
    current_layer_group.value.add_layer(rInflP_layer.value)  # vorher erfolgreich, aber nicht zu resetten: current_layer_group.value.add_layer(combined_layer)

    # Legend: Elevation
    legend_elev_html = widgets.HTML(value=legend_elev._repr_html_())
    legend_elev_control = WidgetControl(widget=legend_elev_html, position="bottomright")

    # Create legend for rivers + sources + WLB
    legend_custom_html = """
    <div style="padding: 10px; background: white; color: black; border: 1px solid gray; border-radius: 5px; font-size: 13px;">
        <b>Legend</b><br>
        <div style="display: flex; align-items: center; margin-top: 5px;">
            <div style="width: 12px; height: 12px; background-color: red; border-radius: 50%; margin-right: 5px;"></div>
            Waterlevel bound
        </div>
        <div style="display: flex; align-items: center; margin-top: 5px;">
            <div style="width: 12px; height: 3px; background-color: blue; margin-right: 5px;"></div>
            Rivers inflow
        </div>
        <div style="display: flex; align-items: center; margin-top: 5px;">
            <div style="width: 12px; height: 12px; background-color: white; border: 1px solid black; border-radius: 50%; margin-right: 5px;"></div>
            Sources
        </div>
    </div>
    """
    legend_widget = widgets.HTML(value=legend_custom_html)
    legend_control = WidgetControl(widget=legend_widget, position="bottomleft")

    tab_controls.value["rInflP"] = legend_control
    control_signals["rInflP"].set(control_signals["rInflP"].value + 1)

    plot_rInflP_status.set("Done")
    rinflp_plot_done.set(True)
    riverinflowdone.set(True)

    riverinflow_layers = LayerGroup(layers=list(current_layer_group.value.layers))  # HIER HIER HIER HIER HIER HIER HIER HIER HIER HIER
    # tab_controls.value["rInflP"] and control_signals["rInflP"]


def reset_rInflP():
    reset_elev()
    if rInflP_layer.value in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(rInflP_layer.value)

    if scatter_layer_g in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(scatter_layer_g)

    if "rInflP" in tab_controls.value:
        legend_control = tab_controls.value["rInflP"]
        if legend_control in m.controls:
            m.remove_control(legend_control)
        tab_controls.value["rInflP"] = None

    # Reset status or signals if needed
    plot_rInflP_status.set("")
    control_signals["rInflP"].set(control_signals["rInflP"].value + 1)
    rinflp_plot_done.set(False)

@solara.component
def Tab_River_Inflow_Points():
    solara.Markdown("**Show River Inflow Points**", style={"color": "inherit"})

    solara.Markdown(
        "**Note**: the underlying elevation data comes from Tab 3. ELEVATION",
        style={"color": "inherit"},
    )

    solara.Button(
        label="Plot river inflow points", on_click=plot_rInflP, continuous_update=True
    )

    if plot_rInflP_status.value == "Plotting":
        solara.Markdown(
            "Preparing river inflow sources... Please wait. This might take a couple of minutes.",
            style={"color": "inherit"},
        )
    elif plot_rInflP_status.value == "Done":
        solara.Markdown("**Done!**", style={"color": "inherit"})
    else:
        solara.Markdown("")

    solara.Button("Reset", on_click=reset_rInflP, disabled=not rinflp_plot_done.value)
    # if not rinflp_plot_done.value:
    #     solara.Markdown("Plot river inflow points first.")

    with solara.Row(justify="end"):
        solara.Button(
            label="Go to Step 7.",
            on_click=lambda: selected_tab.set("subgrid"),
            disabled=not riverinflowdone.value,
        )


# Tab_River_Inflow_Points()

# ===========================================================================
# 8) Land roughness and infiltration
# ===========================================================================
LRI_status = solara.reactive("Idle")


def LRI_get_data():
    global datasets_rgh
    LRI_status.set("Running")
    set_environ("infiltration")
    sf.infiltration.create_cn(
        data_dict["infiltration"], antecedent_moisture="avg"
    )  # Setup soil infiltration # UPDATE # sf.setup_cn_infiltration(data_dict['infiltration'], antecedent_moisture='avg')
    set_environ("lulc")
    datasets_rgh = [{"lulc": data_dict["lulc"]}]  # Setup surface roughness
    # sf.grid.data_vars.keys() # check all variables in the sf.grid dataset
    info_retrieved_done.set(True)
    LRI_status.set("Done")


# ===========================================================================
# 9) Subgrid
# ===========================================================================
zzmin_status = solara.reactive("Idle")
subgrid_layer = solara.reactive(LayerGroup())
subgrid_plot_done = solara.reactive(False)
info_retrieved_done = solara.reactive(False)
nr_subgrid_pixels = solara.reactive(6)


def plot_zzmin():
    global scatter_layer_sg
    zzmin_status.set("Running")

    if subgrid_layer.value in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(subgrid_layer.value)

    sf.subgrid.create(  # UPDATE # sf.setup_subgrid(
        elevation_list=datasets_dep,  # The elevation data
        roughness_list=datasets_rgh,  # The roughness data
        nr_subgrid_pixels=nr_subgrid_pixels.value,  # TO BE SET BY USER!!!!!
        write_dep_tif=True,  # Whether to write the subgrid elevation data
        write_man_tif=True,  # Whether to write the subgrid roughness data
    )

    step_sg = solara.reactive(7)
    zzmin = sf.subgrid.data.z_zmin # UPDATED FROM: zzmin = sf.subgrid.z_zmin

    transformer = Transformer.from_crs(zzmin.rio.crs, "EPSG:4326", always_xy=True)
    X, Y = np.meshgrid(zzmin.x.values, zzmin.y.values)
    lon, lat = transformer.transform(X, Y)

    colormap = LinearColormap(
        colors=["blue", "white", "red"],
        vmin=-float(np.max(zzmin)),  # float(np.min(zzmin)),
        vmax=float(np.max(zzmin)),
        caption="z_zmin",
    )

    step_sg.value = 10  #########################################
    scatter_layer_sg = LayerGroup()
    for i in range(0, zzmin.values.shape[0], step_sg.value):
        for j in range(0, zzmin.values.shape[1], step_sg.value):
            val = zzmin.values[i, j]
            if np.isnan(val):
                continue
            color = colormap(val)

            marker = CircleMarker(
                location=(lat[i, j], lon[i, j]),
                radius=2,
                color=color,
                fill_color=color,
                fill_opacity=0.4,
            )
            scatter_layer_sg.add_layer(marker)

    # LEGEND ##############
    vmin = np.round(-float(np.max(zzmin)))
    vmax = np.round(float(np.max(zzmin)))
    midpoint = 0

    legend_zzmin = LinearColormap(
        colors=["blue", "white", "red"],
        # index=all_vals,
        vmin=vmin,
        vmax=vmax,
        caption="z_zmin",
    )

    # ADD TO MAP ################################################################
    if subgrid_layer.value in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(subgrid_layer.value)
    subgrid_layer.set(scatter_layer_sg)
    # current_layer_group.value.add_layer(subgrid_layer.value) # vorher erfolgreich, aber nicht zu resetten: current_layer_group.value.add_layer(scatter_layer_sg)
    current_layer_group.value.add_layer(scatter_layer_sg)

    if src_river_layer in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(src_river_layer)
    # # subgrid_layer.set(src_river_layer) # das hier war raus
    # current_layer_group.value.add_layer(subgrid_layer.value) # vorher erfolgreich, aber nicht zu resetten: current_layer_group.value.add_layer(src_river_layer)
    current_layer_group.value.add_layer(src_river_layer)

    legend_html = widgets.HTML(value=legend_zzmin._repr_html_())
    legend_control = WidgetControl(widget=legend_html, position="bottomright")
    tab_controls.value["subgrid"] = legend_control
    control_signals["subgrid"].set(control_signals["subgrid"].value + 1)

    zzmin_status.set("Done")
    subgrid_plot_done.set(True)
    roughnesssubgriddone.set(True)


def reset_subgrid():
    if subgrid_layer.value in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(subgrid_layer.value)

    if scatter_layer_sg in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(scatter_layer_sg)

    if src_river_layer in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(src_river_layer)

    if "subgrid" in tab_controls.value:
        legend_control = tab_controls.value["subgrid"]
        if legend_control in m.controls:
            m.remove_control(legend_control)
        tab_controls.value["subgrid"] = None

    # Reset status or signals if needed
    control_signals["subgrid"].set(control_signals["subgrid"].value + 1)
    zzmin_status.set("")
    nr_subgrid_pixels.set(6)
    subgrid_plot_done.set(False)

@solara.component
def Tab_Subgrid():
    solara.Markdown(
        "**Get information about land roughness and soil infiltration**",
        style={"color": "inherit"},
    )
    solara.Button(label="Retrieve information", on_click=LRI_get_data)  # , continuous_update=True)
    if LRI_status.value == "Running":
        solara.Markdown("Retrieving information... Please wait.", style={"color": "inherit"})
    elif LRI_status.value == "Done":
        solara.Markdown("**Done!**", style={"color": "inherit"})

    ###############################

    solara.Markdown(
        "**Setting the number of subgrid pixels:** Ratio of grid resolution to DEM resolution.",
        style={"color": "inherit"},
    )
    solara.InputInt("Number of subgrid pixels", value=nr_subgrid_pixels)  # , continuous_update=True)
    solara.Markdown(f"**Selected**: {nr_subgrid_pixels.value}", style={"color": "inherit"})
    # with solara.Row():
    solara.Button("Set to Default", on_click=lambda: nr_subgrid_pixels.set(6))

    solara.Button(label="Plot", on_click=plot_zzmin, disabled=not info_retrieved_done.value)  # , continuous_update=True)
    if not info_retrieved_done.value:
        solara.Markdown("Retrieve information first.", style={"color": "inherit"})
    if zzmin_status.value == "Running":
        solara.Markdown("Plot zzmin... Please wait. This might take a couple of minutes.",style={"color": "inherit"})
    elif zzmin_status.value == "Done":
        solara.Markdown("**Done!**", style={"color": "inherit"})
    else:
        solara.Markdown("")

    solara.Button("Reset", on_click=reset_subgrid, disabled=not subgrid_plot_done.value)
    # if not subgrid_plot_done.value:
    #     solara.Markdown("Plot subgrid first.")

    with solara.Row(justify="end"):
        solara.Button(
            label="Go to Step 8.",
            on_click=lambda: selected_tab.set("obs"),
            disabled=not roughnesssubgriddone.value,
        )

# Tab_Subgrid()

# ===========================================================================
# 10) Obs stations
# ===========================================================================
# roughnesssubgriddone.set(True)
obs_layer = solara.reactive(LayerGroup())
obs_points_fn = solara.reactive("C:\\")  # ("C:\\") # HIER PATH ÄNDERN


def empty_gdf():
    return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")


def show_imported_ob_loc():
    global obs
    sf.observation_points.clear # UPDATE FROM: sf.geoms.pop("obs", None)

    sf.observation_points.create(
        locations=obs_points_fn.value
    )  # UPDATE # sf.setup_observation_points(locations=obs_points_fn.value)
    obs = sf.observation_points.data # UPDATE FROM: obs = sf.geoms["obs"]

    transformer = Transformer.from_crs(obs.crs, "EPSG:4326", always_xy=True)

    imp_obs_layer = LayerGroup()
    icon_bino = AwesomeIcon(
        name="binoculars", marker_color="red", icon_color="black", spin=False
    )

    for idx, geom in enumerate(obs.geometry):
        if geom.geom_type == "Point":
            lon, lat = transformer.transform(geom.x, geom.y)
            marker = Marker(icon=icon_bino, location=(lat, lon), draggable=False)
            imp_obs_layer.add_layer(marker)
    # mmm.add_layer(imp_obs_layer) # ADJUST TO STRUCTURE OF LAYERS!!!

    # ADD TO MAP ################################################################
    if obs_layer.value in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(obs_layer.value)
    obs_layer.set(imp_obs_layer)
    current_layer_group.value.add_layer(obs_layer.value)  # .add_layer(scatter_layer_sg)


def remove_imported_ob_loc():
    global obs, all_obs_loc
    if obs_layer.value in current_layer_group.value.layers:
        current_layer_group.value.remove_layer(obs_layer.value)
    obs_layer.set(LayerGroup())
    obs = None
    # sf.geoms["obs"] = empty_gdf() # [] # sf.geoms["obs"] = None # sf.geoms.pop("obs", None)
    sf.observation_points.clear()  # sf.geoms.pop("obs", None);
    all_obs_loc = empty_gdf()


place_obs_enabled = solara.reactive(False)
locations = []


def handle_map_click(**kwargs):
    # place_obs.set("activated")
    if not place_obs_enabled.value:
        return
    if kwargs.get("type") == "click":
        latlng = kwargs.get("coordinates")
        user_obs_loc = Marker(location=latlng, draggable=False)
        m.add_layer(user_obs_loc)
        locations.append(latlng)

        # remove marker on click
        def remove_marker(**_):
            if user_obs_loc in m.layers:
                m.remove_layer(user_obs_loc)
            if user_obs_loc.location in locations:
                locations.remove(user_obs_loc.location)

        user_obs_loc.on_click(remove_marker)

save_obs_status = solara.reactive("Idle")


def fix_obs_loc():
    global all_obs_loc
    save_obs_status.set("Running")
    try:
        obs_exists = "obs" in globals() and obs is not None and not obs.empty
    except Exception:
        obs_exists = False

    loc_exists = "locations" in globals() and len(locations) > 0
    gdfs = []

    if obs_exists:
        obs_wgs = obs.to_crs("EPSG:4326")
        gdfs.append(obs_wgs)
        obs_wgs = obs

    if loc_exists:
        # locations are already lat/lon → build GeoDataFrame in EPSG:4326
        user_geoms = [Point(lon, lat) for lat, lon in locations]
        user_obs = gpd.GeoDataFrame(geometry=user_geoms, crs="EPSG:4326")
        gdfs.append(user_obs)

    if gdfs:
        print("building all_obs_loc")
        all_obs_loc = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True), crs="EPSG:4326")
        all_obs_loc_crs = obs.to_crs(sf.grid.crs)
        sf.observation_points.set(all_obs_loc_crs, merge=False) # UPDATE FROM: sf.geoms["obs"] = all_obs_loc
    else:
        print("no obs, no locations -> empty")
        all_obs_loc = empty_gdf()
        all_obs_loc_crs = empty_gdf()
        sf.observation_points.clear # UPDATE FROM:sf.geoms["obs"] = empty_gdf()

    # disable interactions again
    m.interaction_callbacks = []
    save_obs_status.set("Done")
    obsdone.set(True)

@solara.component
def Tab_Observations():
    solara.Markdown(
        "**Observation Locations:** Import existing observation locations and add new ones on the map.",
        style={"color": "inherit"},
    )
    solara.Markdown("**Select Model:**", style={"color": "inherit"})
    solara.InputText("Model directory", value=obs_points_fn, continuous_update=True)
    path_imported_obs = Path(obs_points_fn.value)
    if obs_points_fn.value:
        if not obs_points_fn.value.endswith(".geojson"):
            solara.Error(
                label='Error: File must end with ".geojson"',
                text=False,
                dense=True,
                outlined=True,
                icon=False,
            )
        elif not path_imported_obs.exists():
            solara.Error("File does not exist.")

    with solara.Row(gap="25px"):
        solara.Button(label="Import & Show", on_click=show_imported_ob_loc)
        solara.Button(label="Remove", on_click=remove_imported_ob_loc)

    solara.Markdown("Imported observation locations are shown in red.", style={"color": "inherit"})

    # solara.Button(label="Place additional observation locations on map",on_click=enable_placing_locs)
    solara.Switch(label="Enable placing markers (in blue)", value=place_obs_enabled)
    # solara.use_effect(lambda: (locations.clear(),m.interaction_callbacks.clear(),m.on_interaction(handle_map_click) if place_obs_enabled.value else None))

    if place_obs_enabled.value == "activated":
        solara.Markdown(
            "Click on map to place marker. Click on marker to remove.",
            style={"color": "inherit"},
        )
    else:
        solara.Markdown("")

    solara.Button(label="Save all locations", on_click=fix_obs_loc)
    if save_obs_status.value == "Running":
        solara.Markdown(
            "Saving Observations... Please wait.", style={"color": "inherit"}
        )
    elif save_obs_status.value == "Done":
        solara.Markdown("**Done!**", style={"color": "inherit"})

    with solara.Row(justify="end"):
        solara.Button(
            label="Go to Step 9.",
            on_click=lambda: selected_tab.set("forcing"),
            disabled=not obsdone.value,
        )

# Tab_Observations()

# ===========================================================================
# 11) Set-up forcings
# ===========================================================================
wl_distance = solara.reactive(10000)
forcing_source_options = ["era5_hourly_destine", "Other (not yet implemented)"]
forcing_source = solara.reactive("era5_hourly_destine")

wl_bnd_forcing_status = solara.reactive("Idle")


def setup_wl_bnd():
    wl_bnd_forcing_status.set("Running")
    sf.water_level.create_boundary_points_from_mask(bnd_dist=wl_distance.value) # UPDATE # sf.setup_waterlevel_bnd_from_mask(distance=wl_distance.value,merge=True)
    wl_bnd_forcing_status.set("Done")


forcings_status = solara.reactive("Idle")


def setup_meteo():
    forcings_status.set("Running")
    set_environ("precip")
    sf.precipitation.create(precip=forcing_source.value, aggregate=False)  # UPDATE # sf.setup_precip_forcing_from_grid(precip=forcing_source.value, aggregate=False)
    sf.pressure.create(press=forcing_source.value)  # UPDATE # sf.setup_pressure_forcing_from_grid(press=forcing_source.value)
    sf.wind.create(wind=forcing_source.value)  # UPDATE # sf.setup_wind_forcing_from_grid(wind=forcing_source.value)
    forcings_status.set("Done")
    forcingdone.set(True)

@solara.component
def Tab_setup_forcings():
    solara.Markdown("**Setup waterlevel boundaries**", style={"color": "inherit"})
    solara.InputInt("Number of subgrid pixels", value=wl_distance)
    solara.Button("Setup waterlevel boundaries", on_click=setup_wl_bnd)

    if wl_bnd_forcing_status.value == "Running":
        solara.Markdown("Setting-up waterlevel boundaries... Please wait.",style={"color": "inherit"})
    elif wl_bnd_forcing_status.value == "Done":
        solara.Markdown("**Done!**", style={"color": "inherit"})

    solara.Markdown("**Setup spatially varying meteo data**", style={"color": "inherit"})
    solara.Select(
        label="forcing??? can this vary??",
        value=forcing_source,
        values=forcing_source_options,
    )  # solara.InputText("forcing???", value=forcing_source, continuous_update=True)
    solara.Button("Setup", on_click=setup_meteo)

    if forcings_status.value == "Running":
        solara.Markdown("Setting-up spatially varying meteo data... Please wait.",style={"color": "inherit"})
    elif forcings_status.value == "Done":
        solara.Markdown("**Done!**", style={"color": "inherit"})

    with solara.Row(justify="end"):
        solara.Button(
            label="Go to Step 10.",
            on_click=lambda: selected_tab.set("model"),
            disabled=not forcingdone.value,
        )

# Tab_setup_forcings()

# ===========================================================================
# 12) Show and Write Model
# ===========================================================================
def show_wlbnd():
    bnd_df = pd.read_csv(
        os.path.join(model_path.value, "sfincs.bnd"),
        delim_whitespace=True,
        header=None,
        names=["x", "y"],
    )
    transformer = Transformer.from_crs(obs.crs, "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(bnd_df["x"].values, bnd_df["y"].values)

    wlbnd_point_layer = LayerGroup()
    text_step = 0.035
    label_markers_wlbnd = []

    for idx, (lon_i, lat_i) in enumerate(
        zip(lon, lat)
    ):  # for lon, lat in list(zip(lon, lat)):
        marker_wl = CircleMarker(
            location=(lat_i, lon_i),  # Note: folium and ipyleaflet use (lat, lon)
            radius=5,
            color="black",
            weight=1,
            fill=True,
            fill_color="grey",
            fill_opacity=1.0,
        )
        wlbnd_point_layer.add_layer(marker_wl)

        # text_step = 0.035
        # label_markers_wlbnd = []

        label_wl = Marker(
            location=(lat_i + text_step, lon_i),  # Slight offset to avoid overlap
            icon=Icon(
                icon_url="data:image/svg+xml;charset=utf-8,"
                + f"<svg xmlns='http://www.w3.org/2000/svg' width='30' height='20'><text x='0' y='15' font-size='20' font-weight='bold' fill='black'>{idx + 1}</text></svg>",
                icon_size=[30, 20],
            ),
        )
        # mmm.add_layer(label)
        wlbnd_point_layer.add_layer(label_wl)
        label_markers_wlbnd.append((label_wl, lat_i, lon_i))

    def update_text_step(change):
        global text_step
        zoom = change["new"]
        if zoom <= 7:
            text_step = 0.035
        elif zoom == 8:
            text_step = 0.025
        elif zoom == 9:
            text_step = 0.015
        elif zoom == 10:
            text_step = 0.01
        else:
            text_step = 0.01 * (0.5 ** (zoom - 10))

        for label, lat, lon in label_markers_wlbnd:
            label.location = (lat + text_step, lon)

    m.observe(update_text_step, names="zoom")

    # if rInflP_layer.value in current_layer_group.value.layers:
    #     current_layer_group.value.remove_layer(rInflP_layer.value)
    # rInflP_layer.set(wlbnd_point_layer)
    # current_layer_group.value.add_layer(rInflP_layer.value)

    # Create legend for rivers + sources + WLB
    legend_custom_html_model = """
    <div style="padding: 10px; background: white; color: black; border: 1px solid gray; border-radius: 5px; font-size: 13px;">
        <b>Legend</b><br>
        <div style="display: flex; align-items: center; margin-top: 5px;">
            <div style="width: 12px; height: 12px; background-color: red; border-radius: 50%; margin-right: 5px;"></div>
            Waterlevel bound
        </div>
        <div style="display: flex; align-items: center; margin-top: 5px;">
            <div style="width: 12px; height: 3px; background-color: blue; margin-right: 5px;"></div>
            Rivers inflow
        </div>
        <div style="display: flex; align-items: center; margin-top: 5px;">
            <div style="width: 12px; height: 12px; background-color: white; border: 1px solid black; border-radius: 50%; margin-right: 5px;"></div>
            Sources
        </div>
        <div style="display: flex; align-items: center; margin-top: 5px;">
            <div style="width: 12px; height: 12px; background-color: grey; border: 1px solid black; border-radius: 50%; margin-right: 5px;"></div>
            Waterlevel Bounds
        </div>
    </div>
    """
    legend_widget_model = widgets.HTML(value=legend_custom_html_model)
    legend_control_model = WidgetControl(
        widget=legend_widget_model, position="bottomleft"
    )

    tab_controls.value["model"] = legend_control_model

    return wlbnd_point_layer


write_model_status = solara.reactive("Idle")

def write_model():
    write_model_status.set("Running")

    sf.write()
    sf_new = SfincsModel(root=sf_root.value, mode="r")
    sf_new.read()

    write_model_status.set("Done")


show_tree = solara.reactive(False)
tree_output = solara.reactive("")


def tree(directory):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        print(f"+ {directory}")
        for path in sorted(directory.rglob("*")):
            depth = len(path.relative_to(directory).parts)
            spacer = "  " * depth
            print(f"{spacer}+ {path.name}")

    return buffer.getvalue()


##############################################################################################################################################


def figure_dis():
    loading_dis.value = True

    def worker():
        f, ax = plt.subplots(figsize=(8, 5), constrained_layout=True, dpi=100)
        for i in range(sf.forcing["dis"].shape[1]):  # 15 indices
            ax.plot(
                sf.forcing["dis"].time, sf.forcing["dis"].values[:, i], label=f"{i + 1}"
            )
        ax.set_xlabel("Time")
        ax.set_ylabel("Discharge [m³/s]")
        ax.legend(title="Index", bbox_to_anchor=(1.05, 1), loc="upper left")
        # f.tight_layout()
        fig_dis.value = f
        loading_dis.value = False
        fig_ready_dis.value = True

    threading.Thread(target=worker).start()


def reset_figure_dis():
    fig_dis.value = None
    fig_ready_dis.value = False
    loading_dis.value = False
show_dis = solara.reactive(False)
loading_dis = solara.reactive(False)
fig_ready_dis = solara.reactive(False)
fig_dis = solara.reactive(None)
show_bzs = solara.reactive(False)
show_precip2d = solara.reactive(False)
show_press2d = solara.reactive(False)
show_wind10u = solara.reactive(False)
show_wind10v = solara.reactive(False)


@solara.component
def Tab_show_write_model():
    solara.Markdown("**Show and Write Model:**", style={"color": "inherit"})

    solara.Button("Write Model", on_click=write_model)
    if write_model_status.value == "Running":
        solara.Markdown("**Running ...** Please wait.", style={"color": "inherit"})
    elif write_model_status.value == "Done":
        solara.Markdown("**Model set-up successfully!**", style={"color": "inherit"})

    solara.Switch(
        label="Show Path Structure",
        value=show_tree,
        disabled=(write_model_status.value != "Done"),
    )
    if show_tree.value:  # tree(Path(sf.root))
        tree_output.value = tree(Path(sf.root))
        solara.Markdown(f"```\n{tree_output.value}\n```", style={"color": "inherit"})

    solara.Markdown(
        "**Show Forcings**, but note: figures might take some seconds to appear.",
        style={"color": "inherit"},
    )

    solara.Switch(
        label="Show SFINCS discharge forcing",
        value=show_dis,
        disabled=(write_model_status.value != "Done"),
    )  #########################################################
    # if show_dis.value: # plt.plot(sf.forcing['dis'].time,sf.forcing['dis'].values)
    #     fig, ax = plt.subplots(figsize=(8, 5))
    #     for i in range(sf.forcing['dis'].shape[1]):  # 15 indices
    #         ax.plot(sf.forcing['dis'].time, sf.forcing['dis'].values[:, i], label=f"{i+1}")
    #     ax.set_xlabel("Time"); ax.set_ylabel("Discharge [m³/s]")
    #     ax.legend(title="Index", bbox_to_anchor=(1.05, 1), loc="upper left")
    #     fig.tight_layout()
    #     # show_dis_status.set("Done")
    #     solara.FigureMatplotlib(fig)
    if loading_dis.value:
        solara.Markdown("⏳ Generating figure...", style={"color": "inherit"})
    if fig_ready_dis.value and fig_dis.value is not None:
        solara.FigureMatplotlib(fig_dis.value)
    solara.use_effect(
        lambda: figure_dis()
        if show_dis.value and not fig_ready_dis.value
        else reset_figure_dis(),
        dependencies=[show_dis.value],
    )

    solara.Switch(
        label="Show SFINCS waterlevel forcing",
        value=show_bzs,
        disabled=(write_model_status.value != "Done"),
    )
    if show_bzs.value:  # plt.plot(sf.forcing['bzs'].time,sf.forcing['bzs'].values)
        fig, ax = plt.subplots(figsize=(8, 5))
        for i in range(sf.forcing["bzs"].shape[1]):  # 15 indices
            ax.plot(
                sf.forcing["bzs"].time, sf.forcing["bzs"].values[:, i], label=f"{i}"
            )
        ax.set_xlabel("Time")
        ax.set_ylabel("Waterlevel [m+ref]")
        ax.legend(title="Index", bbox_to_anchor=(1.05, 1), loc="upper left")
        fig.tight_layout()
        solara.FigureMatplotlib(fig)

    solara.Switch(
        label="Show SFINCS precipitation forcing",
        value=show_precip2d,
        disabled=(write_model_status.value != "Done"),
    )
    if show_precip2d.value:
        fig, ax = plt.subplots(figsize=(8, 5))
        da = sf.forcing["precip_2d"].transpose("time", ...)
        da = da.mean(dim=[da.raster.x_dim, da.raster.y_dim])
        df = da.to_pandas()
        if isinstance(df.index, pd.MultiIndex):
            df = df.unstack(0)
        df.index = mdates.date2num(df.index)
        ax.bar(df.index, df.values, facecolor="darkblue")
        del df, da
        ax.set_xlabel("Time")
        ax.set_ylabel("Mean Precipitation [mm/hr]")
        fig.tight_layout()
        solara.FigureMatplotlib(fig)

    solara.Switch(
        label="Show SFINCS barometric pressure forcing",
        value=show_press2d,
        disabled=(write_model_status.value != "Done"),
    )
    if show_press2d.value:
        fig, ax = plt.subplots(figsize=(8, 5))
        da = sf.forcing["press_2d"].transpose("time", ...)
        da = da.mean(dim=[da.raster.x_dim, da.raster.y_dim])
        df = da.to_pandas()
        if isinstance(df.index, pd.MultiIndex):
            df = df.unstack(0)
        df.index = mdates.date2num(df.index)
        ax.plot(df)
        del df, da
        ax.set_xlabel("Time")
        ax.set_ylabel("Min barometric Pressure [Pa]")
        fig.tight_layout()
        solara.FigureMatplotlib(fig)

    solara.Switch(
        label="Show SFINCS eastward wind forcing",
        value=show_wind10u,
        disabled=(write_model_status.value != "Done"),
    )
    if show_wind10u.value:
        fig, ax = plt.subplots(figsize=(8, 5))
        da = sf.forcing["wind10_u"].transpose("time", ...)
        if da.ndim == 3:
            da = da.mean(dim=[da.raster.x_dim, da.raster.y_dim])
        df = da.to_pandas()
        ax.plot(df)
        del df, da
        ax.set_xlabel("Time")
        ax.set_ylabel("Mean eastward Wind [m/s]")
        fig.tight_layout()
        solara.FigureMatplotlib(fig)

    solara.Switch(
        label="Show SFINCS northward wind forcing",
        value=show_wind10v,
        disabled=(write_model_status.value != "Done"),
    )
    if show_wind10v.value:
        fig, ax = plt.subplots(figsize=(8, 5))
        da = sf.forcing["wind10_v"].transpose("time", ...)
        if da.ndim == 3:
            da = da.mean(dim=[da.raster.x_dim, da.raster.y_dim])
        df = da.to_pandas()
        ax.plot(df)
        del df, da
        ax.set_xlabel("Time")
        ax.set_ylabel("Mean northwards Wind [m/s]")
        fig.tight_layout()
        solara.FigureMatplotlib(fig)

# Tab_show_write_model()

# ===========================================================================
# Final: layout
# ===========================================================================
def lighten_color(hex_color, amount=0.5):
    hex_color = hex_color.lstrip("#")
    r, g, b = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    r, g, b = [int(x + (255 - x) * amount) for x in (r, g, b)]
    return f"#{r:02x}{g:02x}{b:02x}"


selected_tab = solara.reactive("Config")
current_control = solara.reactive(None)


@solara.component
def SettingsTabs():
    solara.use_effect(
        lambda: selected_tab.set(selected_tab.value), [selected_tab.value]
    )

    def update_map_layers_and_controls():
        for layer in list(m.layers[1:]):
            m.remove_layer(layer)
        if selected_tab.value == "model":
            elev_layers_copy = LayerGroup(layers=list(tab_layers["rInflP"].layers))
            current_layer_group.set(elev_layers_copy)
            tab_layers["model"] = elev_layers_copy
            wlbnd_layer = show_wlbnd()
            current_layer_group.value.add_layer(wlbnd_layer)
        else:
            current_layer_group.set(tab_layers[selected_tab.value])
        m.add_layer(current_layer_group.value)
        # controls
        if current_control.value is not None and current_control.value in m.controls:
            m.remove_control(current_control.value)
        if selected_tab.value in tab_controls.value:
            control = tab_controls.value[selected_tab.value]
            if control not in m.controls:
                m.add_control(control)
            current_control.set(control)
        else:
            current_control.set(None)

    solara.use_effect(
        update_map_layers_and_controls,
        [selected_tab.value, control_signals[selected_tab.value].value],
    )

    def get_button_style(tab_name, original_color, font_color):
        if selected_tab.value == tab_name:
            return {
                "background-color": lighten_color(original_color),
                "color": font_color,
            }
        return {"background-color": original_color, "color": font_color}

    with solara.Column(style={"width": "100%", "align-items": "center"}):
        with solara.Sidebar():
            with solara.Column(gap="10px", style={"align-items": "stretch"}):
                solara.Button(
                    "1. Configuration",
                    on_click=lambda: selected_tab.set("Config"),
                    style=get_button_style("Config", "#999999", "black"),
                )
                solara.Button(
                    "2. Model Domain",
                    on_click=lambda: selected_tab.set("ModDom"),
                    style=get_button_style("ModDom", "#999999", "black"),
                )  # , disabled=not configdone.value) #################
                # if not configdone.value:
                #     solara.Markdown("Model needs to be configurated first.")

                solara.Button(
                    "3. Elevation",
                    on_click=lambda: selected_tab.set("Elev"),
                    style=get_button_style("Elev", "#999999", "black"),
                )  # , disabled=not modeldomaindone.value)
                # if not modeldomaindone.value:
                #     solara.Markdown("Model domain needs to be set-up first.")

                solara.Button(
                    "4. Active cells",
                    on_click=lambda: selected_tab.set("ActC"),
                    style=get_button_style("ActC", "#999999", "black"),
                )  # , disabled=not elevationdone.value)
                # if not elevationdone.value:
                #     solara.Markdown("Elevation data needs to be determined first.")

                solara.Button(
                    "5. Waterlevel bound",
                    on_click=lambda: selected_tab.set("wlBnd"),
                    style=get_button_style("wlBnd", "#999999", "black"),
                )  # , disabled=not activecellsdone.value)
                # if not activecellsdone.value:
                #     solara.Markdown("Active cells need to be determined first.")

                solara.Button(
                    "6. River Infow Points",
                    on_click=lambda: selected_tab.set("rInflP"),
                    style=get_button_style("rInflP", "#999999", "black"),
                )  # , disabled=not waterlevelbnddone.value)
                # if not waterlevelbnddone.value:
                #     solara.Markdown("Waterlevel bounds need to be determined first.")

                solara.Button(
                    "7. Land Roughness & Subgrid",
                    on_click=lambda: selected_tab.set("subgrid"),
                    style=get_button_style("subgrid", "#999999", "black"),
                )  # , disabled=not riverinflowdone.value)
                # if not riverinflowdone.value:
                #     solara.Markdown("River Inflow Points need to be determined first.")

                solara.Button(
                    "8. Observation Stations",
                    on_click=lambda: selected_tab.set("obs"),
                    style=get_button_style("obs", "#999999", "black"),
                )  # , disabled=not roughnesssubgriddone.value)
                # if not roughnesssubgriddone.value:
                #     solara.Markdown("First follow the tab 'Land Roughness & Subgrid'.")

                solara.Button(
                    "9. Forcings",
                    on_click=lambda: selected_tab.set("forcing"),
                    style=get_button_style("obs", "#999999", "black"),
                )  # , disabled=not obsdone.value)
                # if not obsdone.value:
                #     solara.Markdown("Set observation stations first.")

                solara.Button(
                    "10. Show and Write Model",
                    on_click=lambda: selected_tab.set("model"),
                    style=get_button_style("model", "#FF5733", "white"),
                )  # , disabled=not forcingdone.value)
                # if not forcingdone.value:
                #     solara.Markdown("Set forcings first.")

    if selected_tab.value == "Config":
        Tab_Configuration()
    elif selected_tab.value == "ModDom":
        Tab_Model_Domain()
    elif selected_tab.value == "Elev":
        Tab_Elevation()
    elif selected_tab.value == "ActC":
        Tab_Active_Cells()
    elif selected_tab.value == "wlBnd":
        Tab_Waterlevel_Bound()
    elif selected_tab.value == "rInflP":
        Tab_River_Inflow_Points()
    elif selected_tab.value == "subgrid":
        Tab_Subgrid()
    elif selected_tab.value == "obs":
        Tab_Observations()
    elif selected_tab.value == "forcing":
        Tab_setup_forcings()
    elif selected_tab.value == "model":
        Tab_show_write_model()
    elif selected_tab.value == "xxx":
        Tabxxx()

@solara.component
def Page():
    # Create the map + layer groups once per session (after import),
    # which avoids the "widget has been closed" startup crash.
    map_widget = solara.use_memo(init_widgets, [])
    with solara.Columns():
        with solara.Column(style={"width": "70%", "min-width": "650px"}):
            display(map_widget)
        with solara.Column(style={"width": "30%", "min-width": "500px"}):
            SettingsTabs()
