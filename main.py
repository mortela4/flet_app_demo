##
# @file flet_demo.py

# @brief Simple 'flet'-based GUI for demo of GUI elements.

import flet
import json
import time
import sys
import logging
import random
import _thread

from flet import (
                    ElevatedButton, IconButton, TextButton, Switch,
                    Dropdown, 
                    Page, 
                    Row, Column, 
                    TextField, Text, 
                    Container, 
                    Divider, VerticalDivider, 
                    AppBar, 
                    FilePicker, FilePickerResultEvent, 
                    ButtonStyle, RoundedRectangleBorder,
                    AlertDialog              
                )

# Logging setup:
# --------------
logging.basicConfig(
    level=logging.INFO,
    encoding='utf-8', 
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("flet_demo.log"),            # TODO: fix re-use of this logger-def in 'wicc_control.py' when it is used as a module!
        logging.StreamHandler(sys.stdout)
    ]
)
#
logger = logging.getLogger()
logger.name = "flet_demo_LOGGER"


# Local Module(s):
#import local_module  


# Versioning
flet_demo_MAJOR_VERSION = 1          # Initial, mock-up version.
flet_demo_MINOR_VERSION = 1          # Added GUI-controls.
flet_demo_SUBMINOR_VERSION = 0       #   
flet_demo_VERSION_STRING = f"{flet_demo_MAJOR_VERSION}.{flet_demo_MINOR_VERSION}.{flet_demo_SUBMINOR_VERSION}"


# Flags:
STAND_ALONE_APP = True  # false = webapp, true = native GUI
USE_WS_TRACE = True
# 
if STAND_ALONE_APP:
    APP_TYPE = flet.FLET_APP
else:
    APP_TYPE = flet.WEB_BROWSER


gstate_holder = None                                   
grun_flag = True         


# =========================== MAIN ===========================

def main(page: Page):
    #
    global gstate_holder
    #
    logger.info(f"Flet demo-GUI ver.{flet_demo_VERSION_STRING} application started.")
    #
    event_log = list()  # List-of-events in the form of tuples, representing individual event-fields
    log_index = 0
    outlets_enabled = False


    def app_close_tasks(e) -> None:
        """ Cleanup on app close or exit (either via "Close"-choice or window-controls) """
        global grun_flag
        #
        grun_flag = False
        logger.info("WICC GUI application exit ...")
    
    

    # Page setup (this is indeed a S.P.A ...):
    page.title = f"Flet demo UI - ver.{flet_demo_VERSION_STRING}"
    page.window.min_height = 600               
    page.window.min_width = 400                
    page.vertical_alignment = "center"
    page.bgcolor = flet.colors.BLACK,
    page.on_disconnect = app_close_tasks 
    page.on_close = app_close_tasks
    page.window.center()

    # ***************************
    # Add GUI elements:
    # ***************************

    # System Monitoring Controls:
    # ===========================
    # System Sensor Data:]
    hr_label = Text("Heart Rate: ", expand=True, style=flet.TextThemeStyle.HEADLINE_MEDIUM)
    hr_output = TextField(label="[bpm]", read_only=True, color=flet.colors.WHITE, bgcolor=flet.colors.BLACK, text_size=20, expand=True)
    #
    velocity_label = Text("Velocity: ", expand=True, style=flet.TextThemeStyle.HEADLINE_MEDIUM, )
    velocity_output = TextField(label="[km/h]", color=flet.colors.WHITE, bgcolor=flet.colors.BLACK, read_only=True,  text_size=20, expand=True)
    #
    distance_label = Text("Distance: ", expand=True, style=flet.TextThemeStyle.HEADLINE_MEDIUM, )
    distance_output = TextField(label="[meters]", color=flet.colors.WHITE, bgcolor=flet.colors.BLACK, read_only=True,  text_size=20, expand=True)
    #
    row1 = Row([hr_label, hr_output], height=200)
    row2 = Row([velocity_label, velocity_output], height=200)
    row3 = Row([distance_label, distance_output], height=200)
    #
    sensor_data_col = Column( [row1, row2, row3], width=300, expand=True)
    # 
    #sensors_view = Container(content=sensor_data_col, bgcolor=flet.colors.BLUE_GREY_900, border=flet.border.all(1, flet.colors.RED), padding=5, margin=5)
    
    # Construct page:
    #page.add(sensors_view)
    """
    page.add(row1)
    page.add( Divider() )
    page.add(row2)
    page.add( Divider() )
    page.add(row3)
    """
    page.add(sensor_data_col)
    page.add( Divider() )
            
    page.appbar = AppBar(
        leading_width=100,
        center_title=False,
        bgcolor=flet.colors.SURFACE_VARIANT,
        #actions=[
        #    IconButton(flet.icons.FILE_COPY, tooltip="Save Log", on_click=lambda _: log_file_pick.save_file() ),
        #    IconButton(flet.icons.RESET_TV, tooltip="Reset Connection", on_click=reset_gui),
        #],
    )
    # Add some value ...
    hr_output.value = "135.7"
    velocity_output.value = "50.58"
    distance_output.value = "1324.6"
    #
    page.update()


# ================== Run GUI ==========================
flet_demo = flet.app(target=main, view=APP_TYPE, name="Flet Demo")
# Resume when GUI closes:
grun_flag = False
logger.info("Flet demo-application exit ...")


