##
# @file wicc_gui.py
# @brief Simple 'flet'-based GUI for interactive, remote testing of 'WICC' charger application over local network.

import flet
import json
import time
import sys
import logging
import websocket
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
        logging.FileHandler("wicc_gui.log"),            # TODO: fix re-use of this logger-def in 'wicc_control.py' when it is used as a module!
        logging.StreamHandler(sys.stdout)
    ]
)
#
logger = logging.getLogger()
logger.name = "WICC_GUI_LOG"


# Local Module(s):
import wicc_control  


# Versioning
WICC_GUI_MAJOR_VERSION = 0          # This is BETA software (and will forever be so??) Only for bench-test by diehard embedded-folks ...
WICC_GUI_MINOR_VERSION = 14         # Changed: no longer selecting TOTAL system charging-capacity(Amps), instead split into 'A' and 'B' outlet-capacity separately.
WICC_GUI_SUBMINOR_VERSION = 0       #   
WICC_GUI_VERSION_STRING = f"{WICC_GUI_MAJOR_VERSION}.{WICC_GUI_MINOR_VERSION}.{WICC_GUI_SUBMINOR_VERSION}"


# Flags:
STAND_ALONE_APP = True  # false = webapp, true = native GUI
USE_WS_TRACE = True
# 
if STAND_ALONE_APP:
    APP_TYPE = flet.FLET_APP
else:
    APP_TYPE = flet.WEB_BROWSER
#
if USE_WS_TRACE:
    websocket.enableTrace(True)     # NOTE: 'enableTrace()' method does NOT seem to exist in newer versions of 'websocket' library!!(???)
    # websocket.enable_debug()      # TODO: investigate this further!! (HOW to use ...???)

WICC_IS_CONNECTED = False
WICC_HAS_AUTHORIZED = False


# Labels
CHARGER_ON_LABEL = "ON"
CHARGER_OFF_LABEL = "OFF"

# Variable-to-Text/Color mapping
onoffTextMap = {True: CHARGER_ON_LABEL, False: CHARGER_OFF_LABEL}
onoffColorMap = {CHARGER_ON_LABEL: flet.colors.BLUE, CHARGER_OFF_LABEL: flet.colors.GREEN}          # TODO: assess - any use of this as we go from 'ElevatedButton' to 'Switch' for ON/OFF-charging control???
cableLockTextMap = {True: "LOCKED", False: "UNLOCKED"}
cableLockColorMap = {"LOCKED": flet.colors.LIME_900, "UNLOCKED": flet.colors.AMBER_ACCENT_100}
stateColorMap = {"UNKNOWN": flet.colors.GREY_500,
                 "DISCONNECTED": flet.colors.WHITE,
                 "UNLOCKED": flet.colors.YELLOW,
                 "FULLY_CONNECTED": flet.colors.GREEN,
                 "READY_TO_CHARGE": flet.colors.CYAN,
                 "CHARGING_STABLE": flet.colors.BLUE,
                 "MANUAL_STOP": flet.colors.LIGHT_GREEN,
                 "VENTILATION_FAULT": flet.colors.ORANGE,
                 "GND_FAULTED": flet.colors.RED,
                 "PWR_FAULTED": flet.colors.RED,
                 "HW_FAULTED": flet.colors.RED}
msgColorMap = {"info": flet.colors.WHITE,
               "thermal": flet.colors.LIGHT_BLUE,
               "humidity": flet.colors.LIGHT_BLUE,
               "motion": flet.colors.ORANGE_500,
               "state_change": flet.colors.YELLOW,
               "error": flet.colors.RED_ACCENT_100,
               "fault": flet.colors.RED_ACCENT_400}
                                     
         
"""
ON/OFF-button:
"Enabled"(=waiting for EV to connect)   --> chargingEnabled-flag=true
"Ready"(=EV connected, but waiting for EV=ready)   --> chargingEnabled-flag=true
"Charging"(selvforklarende) --> chargingEnabled-flag=true
"Stopped"(fremdeles EV=ready) --> chargingEnabled-flag=false
"Disabled"(EV=not ready, eller disconnected)  --> chargingEnabled-flag=false
"""

# Other mappings
OUTLET_TO_NAME = {"A": "out_A", "B": "out_B"} 
NAME_TO_OUTLET = {"out_A": "A", "out_B": "B"}   # The reverse of above dict.
GRID_CONNECT_MAP = { 
    "auto": 1,	        # NOTE: only to avoid mishaps!
	"L1L2N_3T": 2,	    # DELTA 3-phase ('IT') grid connection --> 230V line, 230V phase voltage (230V 3-phase, N-line = L3-line, i.e. wired together)
	"S1S2_1T": 3,       # DELTA 1-phase ('IT') grid connection --> 230V line, 230V phase voltage L1-L2
	"L1N_1T": 4,        # DELTA 1-phase ('IT') grid connection --> 230V line, 230V phase voltage L1-L3
	"S2N_1T": 5,        # DELTA 1-phase ('IT') grid connection --> 230V line, 230V phase voltage L2-L3
	"L1L2L3N_3N": 6,    # STAR 3-phase ('TN') grid connection --> 400V line, 230V phase voltage (400V 3-phase w. N-conductor)
	"L1N_1N": 7,        # STAR 1-phase ('TN') grid connection --> 400V line, 230V phase voltage L1 (L1-N)
	"S2N_1N": 8,        # STAR 1-phase ('TN') grid connection --> 400V line, 230V phase voltage L2 (L2-N)
	"S3N_1N": 9         # STAR 1-phase ('TN') grid connection --> 400V line, 230V phase voltage L3 (L3-N)
}
GRID_CONNECT_TYPES = list( GRID_CONNECT_MAP.keys() )
GRID_CONNECT_OPTIONS = [flet.dropdown.Option(grid_type) for grid_type in GRID_CONNECT_TYPES]
CHARGER_CAPACITIES = [6, 10, 13, 16, 20, 28, 32]
CHARGER_CAPACITIES_OPTIONS = [flet.dropdown.Option(capacity) for capacity in CHARGER_CAPACITIES]

# Globals
chargingIsActivated = {"A": False, "B": False} 
outletLocked = {"A": False, "B": False}         
gridtypeSelected = {"A": "NONE", "B": "NONE"}   
capacitySelected = {"A": 0, "B": 0} 
websock_thread_id = None 
runFlag = False 


def parse_app_info(json_info: str = None) -> str:
    app_info = json.loads(json_info)
    #
    sw_ver = app_info.get("sw_version")
    git_id = app_info.get("sha_id")
    git_branch = app_info.get("branch")
    built_date = app_info.get("build_date")
    built_time = app_info.get("build_time")
    #
    display_info = f"\n\t\t\tSW version: {sw_ver}\n\t\t\tGIT changeset ID: {git_id}\n\t\t\tGIT branch name: {git_branch}\n\t\t\tBuild date: {built_date}\n\t\t\tBuild time: {built_time}"
    #
    return display_info


def parse_wicc_websock_msg(ws_json_msg: str) -> tuple:
    # Convert to dict:
    ws_event_json = json.loads(ws_json_msg)

    # Check:
    if ws_event_json.get("event_type") is None:
        return None

    # Parse: 
    # ------
    state_notification = None
    # Colorization:
    msg_type = ws_event_json.get("event_type")
    event_msg_color = msgColorMap.get(msg_type) 
    if event_msg_color is None:
        # Set to default color:
        event_msg_color = flet.colors.WHITE
    # Event Originator:
    msg_sender = ws_event_json.get("origin")
    if msg_sender is None:
        # Set to default text:
        msg_sender = "Unknown"
    # Event Message:
    msg_content = ws_event_json.get("message")
    if msg_content is None:
        # Set to default text:
        msg_content = "<--- No Data --->"
    # Additional parsing - any state update?
    if msg_type in ["state_change", "fault"]:
        # ASSUMPTION: leading text is 'new charger state:' - and next word is state, w. first 3 letters 'EV_':
        state_notification = msg_content.split()[3]    
        if not state_notification.startswith("EV_"):
            state_notification = None
    # 
    return event_msg_color, msg_sender, msg_content, state_notification     # TODO: rather add a 'fault_notification' (optional) return value field here???


def state_is_faulted(current_state: any) -> bool:
    """ Check if 'current_state' content indicates charger-state=FAULTED. Content can be string OR bytearray. """
    check_bytearr = current_state in [b'GND_FAULTED', b'EV_GND_FAULTED', b'CP_FAULTED', b'EV_CP_FAULTED', b'HW_FAULTED', b'EV_HW_FAULTED', b'PWR_FAULTED', b'EV_PWR_FAULTED'], 
    check_string = current_state in ["FAULTED", "EV_FAULTED", "b'FAULTED'", "b'EV_FAULTED'", "b'CP_FAULTED'", "b'EV_CP_FAULTED'", "b'HW_FAULTED'", "b'EV_HW_FAULTED'", "b'PWR_FAULTED'", "EV_PWR_FAULTED"]
    #
    return check_bytearr or check_string


# =========================== MAIN ===========================

def main(page: Page):
    #
    global outlets_enabled
    #
    logger.info(f"WICC charger-GUI ver.{WICC_GUI_VERSION_STRING} application started.")
    #
    event_log = list()  # List-of-events in the form of tuples, representing individual event-fields
    log_index = 0
    outlets_enabled = False


    def app_close_tasks(e) -> None:
        """ Cleanup on app close or exit (either via "Close"-choice or window-controls) """
        global runFlag
        #
        runFlag = False
        logger.info("WICC GUI application exit ...")
        #
        if not WICC_IS_CONNECTED:
            logger.info("App was not connected to charger system - nothing to do ...")
            return
        if not WICC_HAS_AUTHORIZED:
            logger.info("App was not authorized on charger system - nothing to do ...")
            return
        # Connected and authorized:
        logger.info("Auto-logout, because app was connected and authorized on charger system ...")
        logout_ok, auth_status = wicc_control.wicc_logout()                                             # TODO: supply user & password from GUI here!!
        #
        if logout_ok:     
                logger.info("Disconnecting from websockets ...")
                try:
                    disconnect_ws_monitor()                                
                    logger.info("Successfully logged out of charger system!")
                except Exception as exc:
                    logger.info(f"Websocket disconnect failed - cause: {exc}")
        else:
            logout_failed_txt = f"Logout from charger system failed - system may be unusable!!\nAuth-status: {auth_status}"
            logger.error(logout_failed_txt)
    

    # Page setup (this is indeed a S.P.A ...):
    page.title = f"WICC Control Center UI - ver.{WICC_GUI_VERSION_STRING}"
    page.window_min_height = 1150               # Should be OK w. 'WUXGA' displays ... (or 'FHD+' --> vpix=1280) - but not so much w. std. 'full-HD' displays (only vpix=1080)
    page.window_min_width = 1850                # Should be OK w. full-HD displays ... (hpix=1920)
    page.vertical_alignment = "center"
    page.bgcolor = flet.colors.WHITE
    page.on_disconnect = app_close_tasks 
    page.on_close = app_close_tasks
    page.window_center()

    # Connection-part:
    # ================
    def check_port_input(e):
        # TODO: some port-validation here!
        pass

    def get_app_info():
        wicc_control.HOST_NAME = host_name_input.value
        if wicc_control.HOST_NAME == "" or wicc_control.HOST_NAME is None:
            wicc_control.HOST_NAME = "localhost"
        #
        try:
            wicc_control.PORT_NUM = int(port_num_input.value)
        except Exception:
            # Show pop-up dialog here?
            wicc_control.PORT_NUM = 18082   # Use default if error ...
        # Make connection:
        try:
            app_info = wicc_control.wicc_appinfo()
        except Exception:
            app_info = None 
        #
        return app_info


    def update_authorization_status(user_is_authorized: bool = False) -> None:
        if user_is_authorized:
            authorization_status.bgcolor = flet.colors.GREEN
            authorization_status.value = "Logged in"
        else:
            authorization_status.bgcolor = flet.colors.RED
            authorization_status.value = "Login FAILED"
        #
        page.update()


    # Target Connect: 
    def connect_clicked(e):
        global WICC_IS_CONNECTED
        global WICC_HAS_AUTHORIZED
        #
        app_info = get_app_info()
        #
        if app_info:
            WICC_IS_CONNECTED = True
            app_info_details = parse_app_info( app_info.content )
            app_info_display.value = app_info_details.replace('\t', '')
            logger.info(f"WICC-app details retrieved ---> {app_info_details}")
        else:
            WICC_IS_CONNECTED = False
            app_info_display.value = "<CONNECTION ATTEMPT FAILED!>"
        # Update GUI to show app-info:
        page.update()
        #
        if WICC_IS_CONNECTED:
            auth_ok, auth_status = wicc_control.wicc_login()         # TODO: supply user & password from GUI here!!
            WICC_HAS_AUTHORIZED = auth_ok
            # Can only attempt charger-login IF connection=OK:
            if WICC_HAS_AUTHORIZED:                                       
                logger.info("Successfully logged in to charger system!")
                connect_button.disabled = True
                logger.info("Connecting to websockets ...")
                connect_ws_monitor(e)
                # Now OK to enable GUI controls:
                enable_controls()
            else:
                def close_pop_up(e):
                    page.dialog.open = False
                    page.update()
                    logger.info("Continuing ...")
                #
                login_failed_txt = f"Login to charger system failed - cannot use charger!! Auth-msg: {auth_status}"
                logger.info(login_failed_txt)
                login_failed_popup = AlertDialog( title=Text(login_failed_txt), 
                                                actions=[ TextButton( "OK", on_click=close_pop_up ) ],
                                                actions_alignment=flet.MainAxisAlignment.END,
                                                on_dismiss=lambda e: logger.info("Might as well exit GUI here ...") )
                page.dialog = login_failed_popup
                login_failed_popup.open = True
            #
            update_authorization_status(user_is_authorized=WICC_HAS_AUTHORIZED)
        else:
            reset_gui()
    

    # Target disconnect:
    def disconnect_clicked(e):
        global WICC_IS_CONNECTED
        global WICC_HAS_AUTHORIZED
        #
        logout_ok, auth_status = wicc_control.wicc_logout()                      # TODO: supply user & password from GUI here!!
        #
        if logout_ok:     
                logger.info("Disconnecting from websockets ...")
                disconnect_ws_monitor(e)                                
                logger.info("Successfully logged out of charger system!")
                authorization_status.bgcolor = flet.colors.BLUE         # TODO: refactor to use 'update_authorization_status()' instead!!!
                authorization_status.value = "Logged out"
        else:
            def close_pop_up(e):
                page.dialog.open = False
                page.update()
                logger.info("Continuing ...")
            #
            logout_failed_txt = f"Logout from charger system failed - system may be unusable!!\nAuth-status: {auth_status}"
            logger.info(logout_failed_txt)
            logout_failed_popup = AlertDialog( title=Text(logout_failed_txt), 
                                            actions=[ TextButton( "OK", on_click=close_pop_up ) ],
                                            actions_alignment=flet.MainAxisAlignment.END,
                                            on_dismiss=lambda e: logger.info("Might as well exit GUI here ...") )
            page.dialog = logout_failed_popup
            logout_failed_popup.open = True
            #
            authorization_status.bgcolor = flet.colors.RED
            authorization_status.value = "Logout FAILED - \nsystem may be unstable!!"
        #
        connect_button.disabled = False
        page.update()
        #
        # Unconditionally:
        WICC_IS_CONNECTED = False
        WICC_HAS_AUTHORIZED = False
        #
        reset_gui()
    

    # ========================================================
    # *************** WebSocket Comms  ***********************
    # ========================================================

    # ************************ Init ************************
    def ws_thread(*args):
        global ws
        #
        WICC_WS_ENDPOINT = f"ws://{wicc_control.HOST_NAME}:{wicc_control.PORT_NUM}/charger_status"
        #
        ws = websocket.WebSocketApp(url=WICC_WS_ENDPOINT, header={"user": "chargerMan"}, on_open=ws_open, on_message=ws_message, on_error=ws_error, on_close=ws_close)
        #
        ws.run_forever()


    # ****************** WebSocket callbacks ***********************

    def ws_message(web_sock, message):
        logger.info(f"{time.time()} --> Charger message: {message}")
        # Handle message:
        event_fields_info = parse_wicc_websock_msg(message) 
        if event_fields_info:
            # It's an 'event'-message (notification-event):
            handle_event_info(event_fields_info)
        else:
            # It's a 'GET'-request response (= state of both outlets):
            ws_data_json = json.loads(message)
            for outlet in ["out_A", "out_B"]:
                ev_state = ws_data_json.get(outlet)
                ev_state_simple = ev_state.replace("EV_", "")
                if ev_state:
                    state_color = stateColorMap.get(ev_state)
                    # Update state:
                    if "out_A" == outlet:
                        state_A.value = ev_state_simple
                        state_A.bgcolor = state_color
                    else:
                        state_B.value = ev_state_simple
                        state_B.bgcolor = state_color
            # Update GUI:
            page.update()


    def ws_open(web_sock):
        #
        web_sock.send("GET")
        # Update GUI
        websock_monitor.bgcolor = flet.colors.BLACK
        websock_monitor.color = flet.colors.WHITE
        websock_monitor.value = "WICC WebSocket connection established!"
        #
        # enable_controls()     # Assess - this should no longer be necessary, no???


    def ws_error(web_sock, exc: Exception):
        # Update GUI
        websock_monitor.bgcolor = flet.colors.RED_ACCENT
        websock_monitor.color = flet.colors.YELLOW
        websock_monitor.value = f"WebSocket ERROR! Cause: '{exc}'"    # TODO: assess - any point in parsing message?? (TYPE OF ERROR ETC.)
        #
        reset_gui()     # TODO: assess - should this also involve setting login=FAILED for given user???
    

    def ws_close(web_sock, status: int, msg: str):
        """ Triggered when WS-connection is closed. Part of LOGOUT-sequence. """
        # Update GUI
        websock_monitor.bgcolor = flet.colors.YELLOW_200
        websock_monitor.color = flet.colors.RED_ACCENT_700
        if status and msg:
            closing_text = f"WebSocket CLOSED! Status={status}, Closing Message: '{msg}'"    
        else:
            closing_text = f"WebSocket forced CLOSE! Connection attempt failed - no response from server ..."
        # 
        websock_monitor.value = closing_text    # TODO: possibly parse message (e.g. to check for 'clean'/'unclean' exit)
        # Update authorization-status text also:
        authorization_status.value = "Charger System Unavailable!"
        authorization_status.bgcolor = flet.colors.RED_50
        #
        page.update()


    # Event Processing:

    def handle_event_info(event_fields_info: tuple):
        nonlocal log_index
        #
        event_log.append(event_fields_info)
        log_index = len(event_log) - 1
        msg_text_color, from_name, msg_text, new_state = event_fields_info
        # Update GUI:
        ws_data_label.value = f"Log entry no.{log_index}:"
        #
        websock_monitor.value = msg_text
        websock_monitor.color = msg_text_color
        #
        websock_origin.value = from_name

        outlet = from_name.lstrip("out_")

        # Check if update is STATE:
        if new_state:
            # Process state:
            new_state = new_state.replace("EV_", "")
            logger.info(f"{from_name}: new state is '{new_state}'")
            state_color = stateColorMap.get(new_state)
            faulted_state = state_is_faulted(new_state)
            # Set to outlet state-indicator:
            if "out_A" == from_name:
                state_A.value = new_state
                state_A.bgcolor = state_color
                if faulted_state:
                    reset_A.disabled = False
                    # Update internal charging-ON/OFF state and ON/OFF-button to be consistent w. faulted state:
                    chargingIsActivated[outlet] = False
                    # on_off_switch_A.text = onoffTextMap.get(False)
                    # on_off_switch_A.bgcolor = flet.colors.RED
                else:
                    reset_A.disabled = True
            elif "out_B" == from_name:
                state_B.value = new_state
                state_B.bgcolor = state_color
                if faulted_state:
                    reset_B.disabled = False
                    # Update internal charging-ON/OFF state and ON/OFF-button to be consistent w. faulted state:
                    chargingIsActivated[outlet] = False
                    # on_off_switch_A.text = onoffTextMap.get(False)
                    # on_off_switch_A.bgcolor = flet.colors.RED
                else:
                    reset_B.disabled = True
            else:
                pass    # Hmmm - should NEVER happen ...
        #
        page.update()

    # ***************** Connect/Disconnect button-handlers *********************
    
    def connect_ws_monitor(e):
        # Start a new thread for the WebSocket interface - connection(-attempt) will happen at instantiation:
        websock_thread_id = _thread.start_new_thread(ws_thread, ())     # TODO: assess - is this a bad idea in a GUI-app???
        logger.info(f"Started WebSock-thread w. ID={websock_thread_id} ...")


    def disconnect_ws_monitor(e):
        global ws
        # Close WS connection:
        ws.close()
        logger.info("WebSock client-conn closed ...")
        # Update GUI:
        websock_monitor.value = "WICC WebSocket connection closed ..."
        page.update()


    # ========================================================
    # *************** Charger Controls ***********************
    # ========================================================

    def fill_in_request_info(ep_url, data_out, status, data_in) -> None:
        ep_url_display.value = ep_url
        req_data_out.value = data_out
        # TODO: check first if response=None before splitting into 'status' and 'content' (requires changing arguments : status+data_in ==> response).
        req_status_display.value = status
        # Any status < 200 means no connection to server (or, even host ...):
        if status < 200:
            # But status=-1 means TIMEOUT:
            if status < 0:
                req_data_in.value = "<REQUEST TIMED OUT!>"
                # Is connection still alive??
                if get_app_info():
                    pass                # Yep ...
                else:
                    reset_gui()         # Appearently, no ... TODO: re-check this - when is it ACTUALLY hit??? (status=100, 0 or -1 ???)
        else:       
            req_data_in.value = data_in
        # Update relevant part of GUI:
        row_OUT_data.update()
        row_IN_data.update()
        
    
    # GRIDTYPE-selector:
    def grid_type_selected(outlet):
        global gridtypeSelected
        #
        if outlet in gridtypeSelected.keys():
            pass
        else:
            logger.info(f"Outlet: out_{outlet} does NOT exist!! Cannot proceed with charger-outlet grid-connection CONFIG ...")
            return
        #
        if "A" == outlet:
            gridType = grid_type_selector_A.value
            gridtypeSelected["A"] = gridType
        else:
            gridType = grid_type_selector_B.value
            gridtypeSelected["B"] = gridType
        # Commander:
        result = wicc_control.wicc_set_grid_config(chargerName=f"out_{outlet}", grid_type=gridType)
        if result:
            ep_url, req_data, req_response = result
            fill_in_request_info(ep_url=ep_url, data_out=req_data, status=req_response.status_code, data_in=req_response.content)
        #
        page.update()


    # RESET-control of charger-loop: 
    def reset_loop_clicked(outlet: str = None):
        """ Reset the charger-loop. Required after EV-state transition to (EV_)FAULTED! New state=DISCONNECTED. """
        # Check key=outlet:
        if outlet not in ["A", "B"]:
            logger.info(f"Outlet: out_{outlet} does NOT exist!! Cannot proceed with charger-loop RESET (='recover') ...")
            return
        # Check if state=FAULTED on outlet:
        if "A" == outlet:
            current_state = state_A.value
            on_off_button = on_off_switch_A
        else:
            current_state = state_B.value
            on_off_button = on_off_switch_B
        #
        def close_pop_up(e):
            page.dialog.open = False
            page.update()
            logger.info("Continuing ...")
        # TODO: check - this does NOT seem to function properly!! (wrong string for matching???)
        if state_is_faulted(current_state):
            # Commander:
            reset_cmd = "recover"
            ep_url, req_data, req_response = wicc_control.wicc_control(chargerName=f"out_{outlet}", chargerCmd=reset_cmd)
            # Fill in debug&monitoring-panel textfields:
            fill_in_request_info(ep_url=ep_url, data_out=req_data, status=req_response.status_code, data_in=req_response.content)
            post_recover_popup = AlertDialog( title=Text(f"Performed RESET of charger {outlet} after FAULT.\nTo re-enable, press 'ENABLE' button!"), 
                                             actions=[ TextButton( "OK", on_click=close_pop_up ) ],
                                             actions_alignment=flet.MainAxisAlignment.END,
                                             on_dismiss=lambda e: logger.info(f"Performed reset of charger {outlet} ...") 
                                             )
            page.dialog = post_recover_popup
            post_recover_popup.open = True
            # Set background of ON/OFF-button for outlet back to normal 'OFF'-color:
            #on_off_button.bgcolor = onoffColorMap.get(CHARGER_OFF_LABEL)
        else:
            no_recover_txt = f"Current state = '{current_state}' - can only issue a RESET on charger-loop if status=FAULTED!!"
            logger.info(no_recover_txt)
            no_recover_popup = AlertDialog( title=Text(no_recover_txt), 
                                             actions=[ TextButton( "OK", on_click=close_pop_up ) ],
                                             actions_alignment=flet.MainAxisAlignment.END,
                                             on_dismiss=lambda e: logger.info("Continuing ...") )
            page.dialog = no_recover_popup
            no_recover_popup.open = True
        # Update GUI:
        page.update()


    # DISABLE-control: 
    def enable_disable_loop_clicked(outlet: str = None, enable: bool = False):
        """ Enable or Disable the charger-loop. """
        charger_loop_action = "ENABLE" if enable else "DISABLE"
        # Check key=outlet:
        if outlet not in ["A", "B"]:
            logger.info(f"Outlet: out_{outlet} does NOT exist!! Cannot proceed with charger-loop {charger_loop_action} ...")
            return
        # Commander:
        charger_loop_cmd = "enable" if enable else "disable"
        ep_url, req_data, req_response = wicc_control.wicc_control(chargerName=f"out_{outlet}", chargerCmd=charger_loop_cmd)
        # Update status:
        outlets_enabled = enable                        # TODO: check request-STATUS before updating variable!!
        # Fill in debug&monitoring-panel textfields:
        fill_in_request_info(ep_url=ep_url, data_out=req_data, status=req_response.status_code, data_in=req_response.content)
        # Update GUI:
        page.update()

    # ON/OFF-control: 
    def on_off_clicked(outlet: str = None):
        global chargingIsActivated
        #
        toggle_map = {"A": on_off_switch_A, "B": on_off_switch_B}   # TODO: assess - rather pass Switch-instance ref as argument???
        #
        if outlet in chargingIsActivated.keys():
            switch_instance = toggle_map.get(outlet)
        else:
            logger.info(f"Outlet: out_{outlet} does NOT exist!! Cannot proceed with charging START/STOP ...")
            return
        #
        do_charging = switch_instance.value
        chargingIsActivated[outlet] = do_charging
        # DEBUG:
        logger.debug(f"Modified charging-map = {chargingIsActivated}")
        #
        button_text = onoffTextMap.get(do_charging)
        if button_text:
            if "A" == outlet:
                on_off_switch_A.label = button_text
            else:
                on_off_switch_B.label = button_text
        else:
            logger.error(f"No label found from switch-value = {do_charging} --> cannot modify switch label!")
        # Commander:
        start_stop_cmd = "start" if do_charging else "stop"
        ep_url, req_data, req_response = wicc_control.wicc_control(chargerName=f"out_{outlet}", chargerCmd=start_stop_cmd)
        # Fill in debug&monitoring-panel textfields:
        fill_in_request_info(ep_url=ep_url, data_out=req_data, status=req_response.status_code, data_in=req_response.content)
        page.update()
    
 
    # LOCK/UNLOCK-control:
    def lock_unlock_clicked(outlet: str = None, do_lock: bool = False):
        #
        global outletLocked
        #
        if outlet in outletLocked.keys():
            pass
        else:
            logger.error(f"Outlet: out_{outlet} does NOT exist!! Cannot proceed with LOCK/UNLOCK ...")
            return
        # Commander:
        lock_unlock_cmd = "lock" if do_lock else "unlock"
        ep_url, req_data, req_response = wicc_control.wicc_control(chargerName=f"out_{outlet}", chargerCmd=lock_unlock_cmd)
        # GUI:
        # TODO: implement a suitable 'lock status'-field in GUI --> update below as appropriate!!
        if "A" == outlet:
            pass
            #lock_unlock_button_A.text = button_text
            #lock_unlock_button_A.bgcolor = cableLockColorMap.get(button_text)
        else:
            pass
            #lock_unlock_button_B.text = button_text
            #lock_unlock_button_B.bgcolor = cableLockColorMap.get(button_text)
        outletLocked[outlet] = do_lock    
        # Fill in debug&monitoring-panel textfields:
        fill_in_request_info(ep_url=ep_url, data_out=req_data, status=req_response.status_code, data_in=req_response.content)
        #
        page.update()
    

    # GET charger-state:
    def get_state_clicked(outlet: str = None):
        # Commander:
        ep_url, req_data, req_response = wicc_control.wicc_control(chargerName=f"out_{outlet}", chargerCmd="state")
        # Fill in debug&monitoring-panel textfields:
        fill_in_request_info(ep_url=ep_url, data_out=req_data, status=req_response.status_code, data_in=req_response.content)
        # Parse:
        state_name = req_response.content.decode()
        simplified_state_name = state_name.replace("EV_", "")
        state_bg_color = stateColorMap.get(simplified_state_name)
        is_faulted_or_not = state_is_faulted(simplified_state_name) 
        # Show state:
        if "A" == outlet:
            state_A.value = simplified_state_name
            state_A.bgcolor = state_bg_color
            reset_A.disabled = is_faulted_or_not
        else:
            state_B.value = simplified_state_name
            state_B.bgcolor = state_bg_color
            reset_B.disabled = is_faulted_or_not
        #
        page.update()


    # CAPACITY-selector:
    def capacity_selected(outlet: str = None):
        """ SET capacity for a given charger-outlet. """
        global capacitySelected
        # GET value from relevant GUI-object 
        capacity = capacity_selector_A.value if 'A' == outlet else capacity_selector_B.value
        #
        # NOTE: 'value' from Dropdown-widget is ALWAYS a string!! (must be converted!)     
        if capacity:
            capacitySelected[outlet] = int(capacity)    # TODO: assess - necessary to keep value in a globalvar???
            # Commander:
            ep_url, req_data, req_response = wicc_control.wicc_set_capacity(chargerCapacity=capacitySelected.get(outlet), chargerOutletName=OUTLET_TO_NAME.get(outlet))
            # Fill in debug & monitoring-panel textfields:
            fill_in_request_info(ep_url=ep_url, data_out=req_data, status=req_response.status_code, data_in=req_response.content)
        #
        page.update()
    
    
    def get_sensor_data(e) -> None:
        ep_url, req_data, req_response = wicc_control.wicc_get_sensor_data()
        # Fill in debug & monitoring-panel textfields:
        json_data = req_response.content
        fill_in_request_info(ep_url=ep_url, data_out=req_data, status=req_response.status_code, data_in=json_data)
        # Parse data & set to GUI sensordata-fields:
        # ------------------------------------------
        data_dict = json.loads(json_data)
        #
        temp_val = data_dict.get("celcius_temperature")
        hygro_val = data_dict.get("percent_humidity")
        #
        acc_values = data_dict.get("linear_acceleration")
        acc_x_val = acc_values.get("x_axis") 
        acc_y_val = acc_values.get("y_axis") 
        acc_z_val = acc_values.get("z_axis") 
        #
        gyro_values = data_dict.get("angular_acceleration")
        gyro_x_val = gyro_values.get("x_axis") 
        gyro_y_val = gyro_values.get("y_axis") 
        gyro_z_val = gyro_values.get("z_axis") 
        #
        # Update GUI section:
        temp_output.value = f"{temp_val}"
        humidity_output.value = f"{hygro_val}" 
        acc_x_output.value = f"{acc_x_val}"
        acc_y_output.value = f"{acc_y_val}"
        acc_z_output.value = f"{acc_z_val}"
        gyro_x_output.value = f"{gyro_x_val}"
        gyro_y_output.value = f"{gyro_y_val}"
        gyro_z_output.value = f"{gyro_z_val}"
        #
        sensor_data_row.update()    # NOTE: can also use object argument 'e' to update correct section of GUI!!

    
    def update_AB_readout_field(action: str) -> None:
        """
        Helper function for the 3 A/B-readout functions below.
        Send request to API, parse returned voltage/current/energy values, then update relevant UI-fields.
        """
        action_map = { "voltage": (wicc_control.wicc_get_voltage, voltages_row, volt_A, volt_B), 
                      "current": (wicc_control.wicc_get_current, currents_row, current_A, current_B),
                      "energy": (wicc_control.wicc_get_energy, energies_row, energy_A, energy_B) }
        #
        readout_action_tuple = action_map.get(action)
        if readout_action_tuple is None:
            logger.error(f"Readout-type '{action} is non-existent!!")
            return
        #
        readout_action, ui_section, ui_A_field, ui_B_field = readout_action_tuple 
        #
        ep_url, req_data, req_response = readout_action()
        # Fill in debug & monitoring-panel textfields:
        json_data = req_response.content
        fill_in_request_info(ep_url=ep_url, data_out=req_data, status=req_response.status_code, data_in=json_data)
        # Dissect values:
        data_dict = json.loads(json_data)
        val_A = data_dict.get("out_A")
        val_B = data_dict.get("out_B")
        # To terminal:
        logger.debug(f"{action}:\nA = {val_A}V\nB = {val_B}V")
        # Show in GUI:
        ui_A_field.value = f"{val_A}"
        ui_B_field.value = f"{val_B}"
        # Update only relevant part of GUI:
        ui_section.update()
    

    # VOLTAGEs-readout:
    def get_voltages(e):
        update_AB_readout_field("voltage")
        

     # CURRENTs-readout:
    def get_currents(e):
        update_AB_readout_field("current")
        
    
    # ENERGY(kWh)-readout:
    def get_energy_consumption(e):
        update_AB_readout_field("energy")

   
    # Log-control:
    def show_next_or_prev_log_entry(go_up: bool):
        nonlocal log_index
        nonlocal event_log
        #
        if go_up:
            # Get previous (less recent) log entry UNLESS we are at the least recent(=oldest) one, i.e. FIRST entry:
            if log_index > 0:
                log_index -= 1  # Go UP in log, i.e. less recent entry (='PREV' action).
            else:
                return
        else:
            # Get next log entry UNLESS we already are at the LAST(=newest) one: 
            if len(event_log) - 2 > log_index:
                log_index += 1   # Go DOWN, i.e. more recent entry (='NEXT' action).
            else:
                return
        # Get event entry:
        txt_color, ev_origin, ev_msg, _ = event_log[log_index]      # Event-log has 4 fields; the last one is 'state' - but that field may be None (and not used in the log-part of GUI so far ... )
        # Update GUI:
        ws_data_label.value = f"Log entry no.{log_index}:"
        #
        websock_monitor.value = ev_msg
        websock_monitor.color = txt_color
        #
        websock_origin.value = ev_origin
        #
        page.update()


    # Log save:
    def save_msg_log(e: FilePickerResultEvent):
        log_file = e.path
        #
        if log_file:
            logger.info(f"Writing WebSocket event-log to file: '{log_file}'")
            # Make snapshot:
            log_snapshot = event_log[:]
            # Create file:
            with open(log_file, 'w') as fp:
                fp.write("WebSocket event log:\n")
                for event_entry in log_snapshot:
                    fp.write(f"{event_entry}\n")
            #
            logger.info(f"Wrote WS-event log to fil '{log_file}' ...")


    # Disable and Enable outlet-Controls.

    def reset_gui():
        """ Disable outlet A & B controls """
        outlets_enabled = False
        logger.info("Resetting Connection and GUI ...")
        #
        con_A.disabled = True
        state_A.value = "UNKNOWN"
        #
        con_B.disabled = True
        state_B.value = "UNKNOWN"
        #
        #capacity_selectors_row.disabled = True
        capacity_selector_A.disabled = True 
        capacity_selector_B.disabled = True
        # 
        app_info_display.value = "<CONNECTION LOST OR TERMINATED!>"
        # Update GUI:
        page.update()


    def enable_controls():
        """ Enable outlet A & B controls """
        outlets_enabled = True
        con_A.disabled = False
        con_B.disabled = False
        #capacity_selectors_row.disabled = False
        capacity_selector_A.disabled = False 
        capacity_selector_B.disabled = False
        # Update GUI:
        page.update()
    

    # ***************************
    # Add buttons and drop-downs:
    # ***************************

    # Common GUI elements (i.e. not specific for an outlet)
    # -----------------------------------------------------
    # Connection details:
    host_name_input = TextField(value="", label="Hostname or IP:", read_only=False, height=50)
    port_num_input = TextField(value="", label="Port number:", read_only=False, on_change=check_port_input, height=50)
    connection_details = Column( [host_name_input, port_num_input] )
    #
    # User credentials:
    user_name_input = TextField(value="", label="User:", read_only=False, height=50)
    password_input = TextField(value="", label="Password:", read_only=False, height=50 )
    user_details = Column( [user_name_input, password_input] )
    #
    connect_button = ElevatedButton(text="Charger API Login", on_click=connect_clicked, color=flet.colors.BLACK, bgcolor=flet.colors.CYAN, height=50, style=ButtonStyle(shape=RoundedRectangleBorder(radius=5)) )
    #
    app_info_display = TextField(label="Application Info:", value="<NOT CONNECTED>", multiline=True, min_lines=5, read_only=True, expand=True, height=100, width=600, bgcolor=flet.colors.GREY_200, color=flet.colors.BLACK)
    # 
    authorization_status = TextField(label="Authorization Status:", value="Waiting for login", multiline=True, min_lines=5, read_only=True, expand=True, height=100, width=600, bgcolor=flet.colors.GREY_200, color=flet.colors.BLACK)
    #
    disconnect_button = ElevatedButton(text="Charger API Logout", on_click=disconnect_clicked, color=flet.colors.BLACK, bgcolor=flet.colors.CYAN_500, height=50, style=ButtonStyle(shape=RoundedRectangleBorder(radius=5)) )
    # Add all connection-controls in a row:
    charger_connect_infos = Row(
        [
            connection_details,
            user_details,
            connect_button,
            app_info_display,
            authorization_status,
            disconnect_button
        ],
        alignment="center",
        height=120,
        width = 1400,
    )  
    #

    # System-wide setup controls:
    capacity_selector_A = Dropdown(
        width=150,
        height=100,
        options=CHARGER_CAPACITIES_OPTIONS,
        label="Select A capacity: ",
        color=flet.colors.BLACK,
        bgcolor=flet.colors.LIGHT_BLUE,
        expand=True,
        on_change=lambda _: capacity_selected(outlet='A'),
        disabled=True,
        )
    
    capacity_selector_B = Dropdown(
        width=150,
        height=100,
        options=CHARGER_CAPACITIES_OPTIONS,
        label="Select B capacity: ",
        color=flet.colors.BLACK,
        bgcolor=flet.colors.LIGHT_BLUE,
        expand=True,
        on_change=lambda _: capacity_selected(outlet='B'),
        disabled=True,
        )
    
    capacity_selectors_row = Row([capacity_selector_A, capacity_selector_B], width=300, expand=True)
    
    # System Monitoring Controls:
    # ===========================
    # System Sensor Data:
    sensor_data_button = ElevatedButton(text="SensorData", on_click=get_sensor_data, color=flet.colors.BLACK, bgcolor=flet.colors.GREY_200, width=150)
    temp_output = TextField(label="Temp[C]:", read_only=True, expand=True)
    humidity_output = TextField(label="Humidity[%]:", read_only=True, expand=True)
    acc_x_output = TextField(label="X-acc:", read_only=True, expand=True)
    acc_y_output = TextField(label="Y-acc:", read_only=True, expand=True)
    acc_z_output = TextField(label="Z-acc:", read_only=True, expand=True)
    gyro_x_output = TextField(label="X-gyro:", read_only=True, expand=True)
    gyro_y_output = TextField(label="Y-gyro:", read_only=True, expand=True)
    gyro_z_output = TextField(label="Z-gyro:", read_only=True, expand=True)
    sensor_alarm_txt = TextField(label="SensorAlarm:", read_only=True, expand=True)
    #
    sensor_data_row = Row(
        [sensor_data_button, 
         temp_output, 
         humidity_output, 
         acc_x_output,
         acc_y_output,
         acc_z_output,
         gyro_x_output,
         gyro_y_output,
         gyro_z_output,
         sensor_alarm_txt], 
         expand=True)
    # 
    #
    voltages_button = ElevatedButton(text="Voltages", on_click=get_voltages, color=flet.colors.BLACK, bgcolor=flet.colors.GREY_200, width=120)
    volt_A = TextField(label="A:", read_only=True, expand=True)
    volt_B = TextField(label="B:", read_only=True, expand=True)
    voltages_row = Row([voltages_button, volt_A, volt_B], width=300, expand=True)
    #
    currents_button = ElevatedButton(text="Currents", on_click=get_currents, color=flet.colors.BLACK, bgcolor=flet.colors.GREY_200, width=120)
    current_A = TextField(label="A:", read_only=True, expand=True)
    current_B = TextField(label="B:", read_only=True, expand=True)
    currents_row = Row([currents_button, current_A, current_B], width=300)
    #
    energies_button = ElevatedButton(text="Energy", on_click=get_energy_consumption, color=flet.colors.BLACK, bgcolor=flet.colors.GREY_200, width=120)
    energy_A = TextField(label="A:", read_only=True, expand=True)
    energy_B = TextField(label="B:", read_only=True, expand=True)
    energies_row = Row([energies_button, energy_A, energy_B], width=300)

    sysmon_controls_div = Divider(thickness=3)
    
    # Wrap into a column:
    col_system_control_and_monitoring = Column( [capacity_selectors_row, sysmon_controls_div, voltages_row, currents_row, energies_row] )
    
    # Outlet 'A':
    label_A = Text(value="Out A Control: ", selectable=False)
    grid_type_selector_A = Dropdown(
        width=200,
        options=GRID_CONNECT_OPTIONS,
        label="AC grid connection: ",
        color=flet.colors.BLACK,
        bgcolor=flet.colors.LIGHT_BLUE,
        on_change=lambda _: grid_type_selected(outlet="A"),
    )
    on_off_label_A = Text(value="Charge:", selectable=False)
    on_off_switch_A = Switch(label="OFF", value=False, on_change=lambda _: on_off_clicked(outlet="A"))
    switch_A_row = Row([on_off_label_A, on_off_switch_A])
    switch_A_container = Container( content=switch_A_row, border=flet.border.all(2, flet.colors.GREY), 
                                   width=200, height=100,  padding=5, margin=5, alignment=flet.alignment.center_right,
                                    bgcolor=flet.colors.LIGHT_GREEN_50 )
    lock_button_A = ElevatedButton(text="LOCK", on_click=lambda _: lock_unlock_clicked(outlet="A", do_lock=True), 
                                   color=flet.colors.BLACK, bgcolor=cableLockColorMap.get("LOCKED"), 
                                   style=ButtonStyle(shape=RoundedRectangleBorder(radius=10)), width=120 )
    unlock_button_A = ElevatedButton(text="UNLOCK", on_click=lambda _: lock_unlock_clicked(outlet="A", do_lock=False), 
                                     color=flet.colors.BLACK, bgcolor=cableLockColorMap.get("UNLOCKED"), 
                                     style=ButtonStyle(shape=RoundedRectangleBorder(radius=10)), width=120 )
    lock_unlock_controls_A = Column( [ lock_button_A, unlock_button_A] )
    lock_control_A = Container(content=lock_unlock_controls_A, border=flet.border.all(1, flet.colors.BLACK), padding=5, margin=5)
    state_A = TextField(value="UNKNOWN", label="Charger state:", expand=True, bgcolor=stateColorMap.get("UNKNOWN"), width=400)
    get_state_A = ElevatedButton(text="Get state", on_click=lambda _: get_state_clicked(outlet="A"), color=flet.colors.BLACK)
    reset_A = ElevatedButton(text="RESET", on_click=lambda _: reset_loop_clicked(outlet="A"), 
                             color=flet.colors.RED, bgcolor=flet.colors.YELLOW,
                             style=ButtonStyle(shape=RoundedRectangleBorder(radius=10)),
                             height=25 )
    enable_A = ElevatedButton(text="ENABLE", on_click=lambda _: enable_disable_loop_clicked(outlet="A", enable=True), 
                             color=flet.colors.RED, bgcolor=flet.colors.GREEN_900,
                             style=ButtonStyle(shape=RoundedRectangleBorder(radius=10)),
                             height=25 )
    disable_A = ElevatedButton(text="DISABLE", on_click=lambda _: enable_disable_loop_clicked(outlet="A", enable=False), 
                             color=flet.colors.RED, bgcolor=flet.colors.GREY, 
                             style=ButtonStyle(shape=RoundedRectangleBorder(radius=10)),
                             height=25 )
    special_A_controls = Column( [reset_A, enable_A, disable_A], height=100 )
    special_A_ctrl_container = Container( content=special_A_controls, border=flet.border.all(2, flet.colors.GREY) )
    #
    row_A = Row(
            [
                label_A,
                grid_type_selector_A,
                switch_A_container,
                lock_control_A,
                state_A,
                get_state_A,
                special_A_ctrl_container,
            ],
            alignment="center",
            width = 1200,
            expand=True,
        ) 
    #
    con_A = Container(
        content=row_A,
        data="A",
        padding=10,
        margin=10,
        border=flet.border.all(2, flet.colors.BLACK),
        tooltip="Outlet 'A' Control",
        disabled=True,
        )
    # 
    # Outlet 'B':
    label_B = Text(value="Out B Control: ", selectable=False)
    grid_type_selector_B = Dropdown(
        width=200,
        options=GRID_CONNECT_OPTIONS,
        label="AC grid connection:",
        color=flet.colors.BLACK,
        bgcolor=flet.colors.LIGHT_BLUE,
        on_change=lambda _: grid_type_selected(outlet="B"),
    )    
    on_off_label_B = Text(value="Charge:", selectable=False)
    on_off_switch_B = Switch(label="OFF", value=False, on_change=lambda _: on_off_clicked(outlet="B"), 
                                     width=200, height=100)
    switch_B_row = Row([on_off_label_B, on_off_switch_B])
    switch_B_container = Container( content=switch_B_row, border=flet.border.all(2, flet.colors.GREY), 
                                   width=200, height=100,  padding=5, margin=5, alignment=flet.alignment.center_right,
                                    bgcolor=flet.colors.LIGHT_GREEN_50 )
    lock_button_B = ElevatedButton(text="LOCK", on_click=lambda _: lock_unlock_clicked(outlet="B", do_lock=True), 
                                   color=flet.colors.BLACK, bgcolor=cableLockColorMap.get("LOCKED"), 
                                   style=ButtonStyle(shape=RoundedRectangleBorder(radius=10)), width=120 )
    unlock_button_B = ElevatedButton(text="UNLOCK", on_click=lambda _: lock_unlock_clicked(outlet="B", do_lock=False), 
                                     color=flet.colors.BLACK, bgcolor=cableLockColorMap.get("UNLOCKED"), 
                                     style=ButtonStyle(shape=RoundedRectangleBorder(radius=10)), width=120 )
    lock_unlock_controls_B = Column( [ lock_button_B, unlock_button_B] )
    lock_control_B = Container(content=lock_unlock_controls_B, border=flet.border.all(1, flet.colors.BLACK), padding=5, margin=5)
    state_B = TextField(value="UNKNOWN", label="Charger state:", expand=True, bgcolor=stateColorMap.get("UNKNOWN"), width=400)
    get_state_B = ElevatedButton(text="Get state", on_click=lambda _: get_state_clicked(outlet="B"), color=flet.colors.BLACK)
    reset_B = ElevatedButton(text="RESET", on_click=lambda _: reset_loop_clicked(outlet="B"), 
                             color=flet.colors.RED, bgcolor=flet.colors.YELLOW,
                             style=ButtonStyle(shape=RoundedRectangleBorder(radius=10)),
                             height=25 )
    enable_B = ElevatedButton(text="ENABLE", on_click=lambda _: enable_disable_loop_clicked(outlet="B", enable=True), 
                             color=flet.colors.RED, bgcolor=flet.colors.GREEN_900,
                             style=ButtonStyle(shape=RoundedRectangleBorder(radius=10)),
                             height=25 )
    disable_B = ElevatedButton(text="DISABLE", on_click=lambda _: enable_disable_loop_clicked(outlet="B", enable=False), 
                             color=flet.colors.RED, bgcolor=flet.colors.GREY,
                             style=ButtonStyle(shape=RoundedRectangleBorder(radius=10)),
                             height=25 )
    special_B_controls = Column( [reset_B, enable_B, disable_B], height=100 )
    special_B_ctrl_container = Container( content=special_B_controls, border=flet.border.all(2, flet.colors.GREY) )    
    #    
    row_B = Row(
            [
                label_B,
                grid_type_selector_B,
                switch_B_container,
                lock_control_B,
                state_B,
                get_state_B,
                special_B_ctrl_container,
            ],
            alignment="center",
            width = 1200,
            expand=True,
        )   
    
    
    con_B = Container(
        content=row_B,
        padding=10,
        margin=10,
        data="B",
        border=flet.border.all(2, flet.colors.BLACK),
        tooltip="Outlet 'B' Control",
        disabled=True,
        )
    
    # Wrap all outlet-CONTROLs in one, single container:
    col_Outlets = Column( [con_A, con_B] )
    vdiv = VerticalDivider(visible=True, color=flet.colors.BLACK, thickness=3)
    con_Outlets = Container( Row( [col_system_control_and_monitoring, vdiv, col_Outlets] ), height=300)

    # Monitoring Section:
    ep_url_display = TextField(label="Endpoint URL:", expand=True, color=flet.colors.YELLOW, bgcolor=flet.colors.GREY_500, read_only=True)
    req_data_out = TextField(label="Request-data:", expand=True, color=flet.colors.YELLOW, bgcolor=flet.colors.GREY_500, read_only=True)       # data OUT
    row_OUT_data = Row(
            [
                ep_url_display,
                req_data_out,
            ],
            alignment="center",
            width=1000,
            height=200,
            expand=True,
        )   
    req_status_display = TextField(label="Request STATUS:", expand=True, color=flet.colors.YELLOW, bgcolor=flet.colors.GREY_500)
    req_data_in = TextField(label="Received data:", expand=True, color=flet.colors.YELLOW, bgcolor=flet.colors.GREY_500)           # data IN
    row_IN_data = Row(
            [
                req_status_display,
                req_data_in,
            ],
            alignment="center",
            width=1000,
            height=200,
            expand=True,
        )  
    # API_request_monitor = Container(content=[row_OUT_data, row_IN_data])

    # TODO: assess - do we need a 'connect' at all??? (rather auto-connect on startup, as soon as host & port is set up??)
    #websock_connect = ElevatedButton(text="WebSock Connect", on_click=connect_ws_monitor, width=200)      
    #websock_disconnect = ElevatedButton(text="WebSock Disconnect", on_click=disconnect_ws_monitor, width=200)
    #websock_connection_controls = Column( [ websock_connect, websock_disconnect] )
    ws_data_label = Text(value=f"Log entry no.{log_index}: ", selectable=False)
    websock_monitor = TextField(label="Websocket data:", width=800, expand=True, color=flet.colors.WHITE, bgcolor=flet.colors.BLACK, tooltip="Websocket data")
    websock_origin = TextField(label="Originator", width=150, expand=False, color=flet.colors.WHITE, bgcolor=flet.colors.BLACK, tooltip="Event origin")
    websock_log_next = IconButton(icon=flet.icons.ARROW_FORWARD, on_click=lambda _: show_next_or_prev_log_entry(go_up=False), tooltip="NEXT")
    websock_log_prev = IconButton(icon=flet.icons.ARROW_BACK, on_click=lambda _: show_next_or_prev_log_entry(go_up=True), tooltip="PREV")
    #websock_controls = Row([websock_connection_controls, ws_data_label, websock_monitor, websock_origin, websock_log_prev, websock_log_next], expand=True, spacing=10, run_spacing=10 )
    websock_controls = Row([ws_data_label, websock_monitor, websock_origin, websock_log_prev, websock_log_next], expand=True, spacing=10, run_spacing=10 )
    
    # Construct page:
    log_file_pick = FilePicker(on_result=save_msg_log)
    page.overlay.append(log_file_pick)
    page.update()
    log_file_pick.update()

    page.add(charger_connect_infos)
    page.add( Divider() )
    page.add(sensor_data_row)
    page.add( Divider() )
    page.add(con_Outlets)
    page.add( Divider(thickness=3) )
    page.add( Text(value="Request details: ", selectable=False) )
    page.add(row_OUT_data)
    page.add( Divider() )
    page.add( Text(value="Request response: ", selectable=False) )
    page.add(row_IN_data)
    page.add( Divider() )
    page.add(websock_controls)
    page.add( Divider() )
    # NOTE: all page.add()-steps above could be done in 1, single 'page.add(...)' step - but this way, some (small) space is added between GUI elements!
        
    page.appbar = AppBar(
        leading_width=100,
        center_title=False,
        bgcolor=flet.colors.SURFACE_VARIANT,
        actions=[
            IconButton(flet.icons.FILE_COPY, tooltip="Save Log", on_click=lambda _: log_file_pick.save_file() ),
            IconButton(flet.icons.RESET_TV, tooltip="Reset Connection", on_click=reset_gui),
        ],
    )

    page.update()


# ================== Run GUI ==========================
wicc_gui = flet.app(target=main, view=APP_TYPE, name="WICC-test-GUI")
# Resume when GUI closes:
runFlag = False
logger.info("WICC GUI application exit ...")
#
if not WICC_IS_CONNECTED:
    logger.info("App was not connected to charger system - nothing to do ...")
    exit(0)
if not WICC_HAS_AUTHORIZED:
    logger.info("App was not authorized on charger system - nothing to do ...")
    exit(0)
# Connected and authorized:
logger.info("Auto-logout, required - because app was connected and authorized on charger system ...")
logout_ok, auth_status = wicc_control.wicc_logout()                      # TODO: supply user & password from GUI here!!
#
if logout_ok:     
        logger.info("Successfully logged out of charger system!")
        try:
            logger.info("Disconnecting from websockets ...")
            # Close WS connection:
            ws.close()
            logger.info("WebSock client-conn closed ...")                               
        except Exception as exc:
            logger.info(f"Websocket disconnect failed - cause: {exc}")
else:
    logout_failed_txt = f"Logout from charger system failed - system may be unusable!!\nAuth-status: {auth_status}"
    logger.info(logout_failed_txt)

