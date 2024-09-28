import sys
import os
# Add the root directory of your project to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pwd
import time
import asyncio
import argparse
import websockets
import json
import configparser
from skylight.led_controller import LEDController

# skylight_main.py
# The skylight service includes the following functionality:
#  1. Create a server to listen for skylight commands to set specific display modes of the neopixels
#  2. To receive printer status messages from moonraker
#  3. Use the LEDController class to set specific led colors.
#

class SkylightService:
    def __init__(self, config_file):
        # Initialize Skylight config
        config = configparser.ConfigParser()
        config_exists = os.path.exists(config_file)
        if config_exists:
            config.read(config_file)
        # Check if the 'skylight' section exists or if the file doesn't exist
        if not config_exists or 'skylight' not in config:
            self.create_default_config(config, config_file)

        skylight_config = config['skylight']
        self.skylight_host = skylight_config.get('skylight_host', 'localhost')
        self.skylight_port = skylight_config.getint('skylight_port', 6789)
        self.led_count = skylight_config.getint('led_count', 30)
        self.moonraker_host = skylight_config.get('moonraker_host', 'localhost')
        self.moonraker_port = skylight_config.getint('moonraker_port', 7125)
        self.display_updates = skylight_config.getboolean('display_updates', True)
        self.update_interval = skylight_config.getint('update_interval', 5)
        self.retry_interval = skylight_config.getint('retry_interval', 30)
        self.debug = skylight_config.getboolean('debug', False)
        print("display_updates =", self.display_updates)
        print("debug =", self.debug)
        self.set_websocket_url(self.moonraker_host, self.moonraker_port)
        self.skylight_websocket_uri = f"ws://{self.skylight_host}:{self.skylight_port}"

        # Initialize LEDController
        self.led_controller = LEDController(led_count=self.led_count)
        self.led_controller.set_effect(self.led_controller.effects_loop)
        default_effect = [['rainbow', 0, self.led_count, '', '', 0]]
        self.led_controller.set_data_fields(default_effect)
        time.sleep(5)

        self.printer_state = "idle"
        self.current_temp = 0
        self.target_temp = 0
        self.percent_complete = 0
        self.print_progress = 0

    def create_default_config(self, config, config_file, username='pi'):
        config['skylight'] = {
            'skylight_host': 'localhost',   # host controlling the neopixels
            'skylight_port': '6791',        # port to listen for skylight commands
            'led_count': '30',              # number of neopixels
            'moonraker_host': 'localhost',  # host running moonraker
            'moonraker_port': '7125',       # port to query/subscribe for status updates
            'display_updates': 'True',      # display moonraker updates, or not
            'update_interval': '5',         # delay between status updates
            'retry_interval': '30',         # delay to reconnect to moonraker
            'debug': 'False'                # display debug output, or not
        }
        with open(config_file, 'w') as file:
            config.write(file)
        try:
            user_info = pwd.getpwnam(username)
            print(f"user_info = {user_info}")
            os.chown(config_file, user_info.pw_uid, user_info.pw_gid)
        except KeyError:
            print(f"User '{username}' does not exist")

    def set_websocket_url(self, host, port):
        self.websocket_url = f"ws://{host}:{port}/websocket"

    async def connect(self):
        while True:
            try:
                self.connection = await websockets.connect(self.websocket_url)
                # Requested printer objects
                params = {"objects": {"print_stats": None, "display_status": None, "extruder": None}}
                # Subscription request
                subscription_request = {
                    "jsonrpc": "2.0",
                    "method": "printer.objects.subscribe",
                    "params": params,
                    "id": 1
                }

                await self.send_request(subscription_request)
                # Query request for current status
                query_request = {
                    "jsonrpc": "2.0",
                    "method": "printer.objects.query",
                    "params": params,
                    "id": 2
                }
                await self.send_request(query_request)
                if self.debug:
                    print(f"Connected to Moonraker server: {self.websocket_url}")
                return True
            except Exception as e:
                if self.debug:
                    print(f"Connection error: {e}")
            if self.debug:
                print(f"Retrying in {self.retry_interval} seconds...")
            await asyncio.sleep(self.retry_interval)

    async def send_request(self, request):
        await self.connection.send(json.dumps(request))

    async def receive_updates(self):
        last_processed_time = 0
        while True:
            try:
                async for message in self.connection:
                    current_time = time.time()
                    response = json.loads(message)

                    if response.get('method') == "notify_status_update":
                        if self.debug:
                            print(f"receive_updates: status_update = {response.get('params', None)}")
                        status_update = response.get("params", [{}])[0]
                        event_time = response.get("params", [{}, 0])[1]
                        self.process_status_update(status_update, event_time)

                    elif response.get("id") == 2:  # ID used for query response
                        if self.debug:
                            print(f"receive_updates: id = {response.get('id')}")
                        query_response = response.get("result", {})
                        status_update = query_response.get("status", {})
                        event_time = query_response.get("eventtime", 0)
                        self.process_status_update(status_update, event_time)

                    elif response.get('method') == "notify_proc_stat_update":
                        proc_stat = response.get('params', [{}])[0]
                        cpu_temp = proc_stat.get("cpu_temp", 0.0) if proc_stat else None
                        if self.debug:
                            print(f"receive_updates: proc_stat_update ")    #= {response.get('params', None)}")
                            print(f"CPU Temp = {cpu_temp}")

                    elif self.debug:
                        print(f"receive updates: {response.get('method')} = {response.get('params', None)}")

                    if current_time - last_processed_time >= self.update_interval:
                        self.update_led_controller()
                        last_processed_time = current_time

            except websockets.exceptions.ConnectionClosedError:
                if self.debug:
                    print("Connection lost. Attempting to reconnect...")
                await self.connect()

    def process_query_response(self, query_response):
        # Implement the logic to process the initial query response
        pass

    def process_status_update(self, status_update, event_time):
        print(f'status: {status_update}')
        extruder_status = status_update.get("extruder", None)
        if extruder_status:
            self.current_temp = extruder_status.get("temperature", self.current_temp)
            self.target_temp = extruder_status.get("target", self.target_temp)
        print_stats = status_update.get("print_stats", None)
        if print_stats:
            self.printer_state = print_stats.get("state", self.printer_state)
        display_status = status_update.get("display_status", None)
        if display_status:
            self.print_progress = round(display_status.get("progress", self.print_progress) ) #, 4)

    def update_led_controller(self):
        if self.debug:
            print(self.printer_state, self.current_temp, self.target_temp, self.print_progress)
        # standby, printing, paused, cancelled, completed, error
        heater_on = self.target_temp > 0
        warming_up = heater_on and (abs(self.current_temp - self.target_temp) > 5)
        cooling_down = (self.current_temp > 50)
        if heater_on:
            percent = self.current_temp / self.target_temp
        else:
            percent = self.current_temp / 250.0

        if self.printer_state == "printing":
            if warming_up:
                self.update_status_leds("temp", percent)
            else:
                self.update_status_leds("progress", self.print_progress)
        elif self.printer_state == "paused":
            self.update_status_leds("paused")
        elif cooling_down or heater_on:
            self.update_status_leds("temp", percent)
        else:
            self.update_status_leds("idle")

    def update_status_leds(self, mode, percent=0):
        if self.debug:
            print(f"update_status_leds: {mode}  {percent}")

        if not self.led_controller:
            return
        if mode == 'temp':
            self.led_controller.set_data_fields([["fade", percent, self.led_count, "blue", "red", 0]])
        elif mode == 'progress':
            self.led_controller.set_data_fields([["progress", percent, self.led_count, "green", "white", 0]])
        elif mode == 'paused':
            self.led_controller.set_data_fields([["chase", 0, self.led_count, "black", "yellow", 0]])
        elif mode == 'idle':
            self.led_controller.set_data_fields([["chase", 0, self.led_count, "white", "black", 0]])

    async def listen_for_skylight_commands(self, websocket, path):
        while True:
            try:
                async for message in websocket:
                    # Process Skylight commands
                    print(f"Received Skylight command: {message}")
                    try:
                        # Decode the received message
                        data = json.loads(message)
                        print(f"Received data: {data}")

                        # Determine the action and call the appropriate method
                        action = data.get("action")
                        params = data.get("params", {})

                        if action == "set_data_values":
                            self.led_controller.set_data_values(params)
                        elif action == "set_data_fields":
                            self.led_controller.set_data_fields(params)
                        elif action == "start_effects":
                            self.led_controller.start_effects(**params)
                        elif action == "stop_effects":
                            self.led_controller.stop_effects()
                        else:
                            raise ValueError("Invalid action")

                        # Send a confirmation response
                        response = {"status": "success", "action": action}
                    except json.JSONDecodeError:
                        response = {"status": "error", "message": "Invalid JSON format"}
                    except KeyError:
                        response = {"status": "error", "message": "Missing action or parameters"}
                    except ValueError as e:
                        response = {"status": "error", "message": str(e)}
                    except Exception as e:
                        response = {"status": "error", "message": f"An unexpected error occurred: {e}"}

                    await websocket.send(json.dumps(response))

            except Exception as e:
                print(f"Error in Skylight WebSocket: {e}")
                await asyncio.sleep(self.retry_interval)  # Retry after the specified interval

    async def skylight_handler(self):
        async with websockets.serve(self.listen_for_skylight_commands, self.skylight_host, self.skylight_port):
            await asyncio.Future()  # Keeps the server running indefinitely

    def run(self):
        loop = asyncio.get_event_loop()
        while True:
            try:
                connected = loop.run_until_complete(self.connect())
                print(f"connected = {connected}")
                if connected:
                    moonraker_task = loop.create_task(self.receive_updates())
                    skylight_task = loop.create_task(self.skylight_handler())
                    loop.run_until_complete(asyncio.gather(moonraker_task, skylight_task))
            except Exception as e:
                print(f"Error caught in run(): {e}")
            if self.debug:
                print("Attempting to reconnect to Moonraker...")
            time.sleep(self.retry_interval)  # Wait before retrying to connect to Moonraker

# Main entry point
def main():
    # Use argparse to handle command-line arguments
    parser = argparse.ArgumentParser(description="Skylight service configuration")
    parser.add_argument(
        "--config",
        default="/home/pi/printer_data/config/skylight.conf",
        help="Path to the configuration file (default: /home/pi/printer_data/config/skylight.conf)"
    )

    # Parse the arguments
    args = parser.parse_args()

    # Use the config file provided via command line, or fallback to default
    config_file = args.config

    # Initialize and run the Skylight service
    client = SkylightService(config_file)
    client.run()

if __name__ == "__main__":
    main()
