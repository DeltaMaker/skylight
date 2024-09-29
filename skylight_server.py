import sys
import os
import time
# Add the root directory of your project to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import asyncio
from aiohttp import web
from websocket_server.base_websocket_server import BaseWebSocketServer
from websocket_server.base_websocket_client import BaseWebSocketClient
from skylight.led_controller import LEDController
from config.config_manager import ConfigManager

class SkylightServer(BaseWebSocketServer):
    def __init__(self, config_manager, host='0.0.0.0'):
        self.config_manager = config_manager
        skylight_port = self.config_manager.getint('skylight', 'skylight_port', 7120)
        debug = self.config_manager.getboolean('skylight', 'debug', True)
        super().__init__(host, skylight_port, debug)

        led_count = self.config_manager.getint('skylight', 'led_count', 30)
        update_interval = self.config_manager.getint('skylight', 'update_interval', 5)

        self.last_update_time = 0
        self.current_state = {
            "update_interval": update_interval,
            "led_data": {},
            "skylight": {
                "status": "off",
                "chain_count": led_count,
                "display_mode": None,  # temperature, progress, idle, command
                "preset": -1,
                "brightness": 255,
                "intensity": -1,
                "speed": -1,
                "error": None
            },
            "display_formats": {
                "temperature": [("fade", 0, led_count, "blue", "red", 0)],
                "progress": [("progress", 0, led_count, "green", "white", 0)],
                "paused": [("breathe", 0, led_count, "yellow", "black", 0)],
                "ready": [("blend", 0, led_count, "blue", "green", 0)],
                "idle": [("chase", 0, led_count, "white", "black", 0)],
                "rainbow": [("rainbow", 0, led_count, "white", "black", 0)],
                "data": [("output", "1001", 4, "green", "blue", 1),
                         ("breathe", "11101", 5, "blue", "green", 1),
                         ("chase", "0000", 4, "red", "black", 1)]
                }
        }
        self.moonraker_client = BaseWebSocketClient(
            connections=[
                {'moonraker': config_manager.moonraker_uri()}
            ],
            subscriptions={
                'moonraker': {
                    "jsonrpc": "2.0",
                    "method": "printer.objects.subscribe",
                    "params": {
                        "objects": {
                            "print_stat": None,
                            "display_status": ["progress"],
                            "idle_timeout": ["state"],
                            "extruder": ["temperature", "target"],
                            "pause_resume": ["is_paused"]
                        }
                    },
                    "id": 2
                }
            },
            debug=debug
        )
        self.moonraker_client.on_state_update = self.handle_moonraker_update
        self.led_controller = LEDController(led_count=led_count)

    def determine_mode(self):
        temperature = self.moonraker_client.get_state("moonraker.extruder.temperature", 25.)
        target = self.moonraker_client.get_state("moonraker.extruder.target", 0.)
        progress = self.moonraker_client.get_state("moonraker.display_status.progress", 0.)
        state = self.moonraker_client.get_state("moonraker.idle_timeout.state")
        paused = self.moonraker_client.get_state("moonraker.pause_resume.is_paused")
        heater_on = target > 0
        warming_up = target - temperature > 2 and heater_on
        cooling_down = temperature > 50 and not heater_on
        percent = temperature / target if heater_on else temperature / 250
        percent = 0.0 if percent < 0 else 1.0 if percent > 1 else percent

        if paused:
            return "paused", 0

        if not warming_up and progress > 0:
            return "progress", progress

        if heater_on or cooling_down:
            return "temperature", percent

        if state == "Ready" and not heater_on and progress < 0.01:
            return "ready", 0

        if state == "Idle":
            return "idle", 0

        return "rainbow", 0

    async def handle_moonraker_update(self, root, updated_objects):
        if time.time() - self.last_update_time < self.current_state["update_interval"]:
            return
        self.last_update_time = time.time()
        if self.current_state['skylight']['display_mode'] == "skybox":
            return

        try:
            display_mode, percent = self.determine_mode()
            if display_mode != self.current_state['skylight']['display_mode']:
                self.current_state['skylight']['display_mode'] = display_mode
                led_data = {}
                display_format = self.current_state["display_formats"].get(display_mode, [])
                for index, field in enumerate (display_format):
                    mode, value, length, color, bg_color, pad = field
                    led_data[f'field{index + 1}'] = {
                        "mode": mode,
                        "value": value,
                        "length": int(length),
                        "color": color,
                        "bg_color": bg_color,
                        "pad": int(pad)
                    }
                self.led_controller.set_data_fields(display_format)
                self.current_state['led_data'] = led_data

            else:
                led_data = self.current_state['led_data']
                values = []
                for key, field in led_data.items():
                    field['value'] = percent
                    values.append(percent)
                if values:
                    self.led_controller.set_data_values(values)
                #if self.debug:
                #    print(f"display_mode: {display_mode} percent={percent}")
        except:
            print(f'exception in handle_moonraker_update() ')


    def update_status_leds2(self, mode, percent=0):
        chain_count = self.get_state("skylight.chain_count", 1)
        if self.debug:
            print(f"update_status_leds: {mode} {chain_count} percent={percent}")

        if not self.led_controller:
            return
        if mode == 'temperature':
            self.led_controller.set_data_fields([["fade", percent, chain_count, "blue", "red", 0]])
        elif mode == 'progress':
            self.led_controller.set_data_fields([["progress", percent, chain_count, "green", "white", 0]])
        elif mode == 'paused':
            self.led_controller.set_data_fields([["breath", percent, chain_count, "black", "yellow", 0]])
        elif mode == 'idle':
            self.led_controller.set_data_fields([["chase", 0, chain_count, "white", "black", 0]])
        elif mode == 'rainbow':
            self.led_controller.set_data_fields([["rainbow", 0, chain_count, "white", "black", 0]])

    def add_custom_routes(self, router):
        """Hook method for adding custom routes in derived classes."""
        router.add_route('*', '/skylight/{tail:.*}', self.process_skylight_command)

    async def process_skylight_command(self, request):
        path = request.path
        query_params = request.query
        post_params = {}

        if request.method == 'POST':
            try:
                post_params = await request.json()
            except:
                post_params = {}

        if path == "/skylight/status" and request.method == 'GET':
            return web.json_response(self.current_state)

        if path == "/skylight/on" and request.method == 'POST':
            self.current_state["skylight"]["status"] = "on"
            return web.json_response(self.current_state["skylight"])

        if path == "/skylight/off" and request.method == 'POST':
            self.current_state["skylight"]["status"] = "off"
            return web.json_response(self.current_state["skylight"])

        if path == "/skylight/toggle" and request.method == 'POST':
            current_status = self.current_state["skylight"]["status"]
            self.current_state["skylight"]["status"] = "off" if current_status == "on" else "on"
            return web.json_response(self.current_state["skylight"])

        if path == "/skylight/control" and request.method in ['GET', 'POST']:
            combined_params = {**query_params, **post_params}

            if "brightness" in combined_params:
                self.current_state["skylight"]["brightness"] = int(combined_params["brightness"])
            if "intensity" in combined_params:
                self.current_state["skylight"]["intensity"] = int(combined_params["intensity"])
            if "speed" in combined_params:
                self.current_state["skylight"]["speed"] = int(combined_params["speed"])
            if "preset" in combined_params:
                self.current_state["skylight"]["preset"] = int(combined_params["preset"])
            if "action" in combined_params:
                action = combined_params["action"]
                if action == 'on':
                    self.current_state["skylight"]["status"] = "on"
                elif action == 'off':
                    self.current_state["skylight"]["status"] = "off"
                elif action == 'toggle':
                    current_status = self.current_state["skylight"]["status"]
                    self.current_state["skylight"]["status"] = "off" if current_status == "on" else "on"

            return web.json_response(self.current_state["skylight"])

        if path == "/skylight/set_data" and request.method in ['GET', 'POST']:
            combined_params = {**query_params, **post_params}

            led_data = {}
            for key, value in combined_params.items():
                try:
                    mode, value, length, color, bg_color, pad = value.split(',')
                    led_data[key] = {
                        "mode": mode,
                        "value": float(value),
                        "length": int(length),
                        "color": color,
                        "bg_color": bg_color,
                        "pad": int(pad)
                    }
                except ValueError:
                    return web.Response(status=400, text=f"Invalid format for field {key}")

            self.current_state["led_data"] = led_data
            return web.json_response({"status": "success", "led_data": self.current_state["led_data"]})

        if path == "/skylight/set_value" and request.method in ['GET', 'POST']:
            combined_params = {**query_params, **post_params}

            for key, value in combined_params.items():
                if key in self.current_state["led_data"]:
                    try:
                        self.current_state["led_data"][key]["value"] = float(value)
                    except ValueError:
                        return web.Response(status=400, text=f"Invalid value format for field {key}")

            return web.json_response({"status": "success", "led_data": self.current_state["led_data"]})

        return web.Response(status=404, text=f"{path} Not Found")

    async def start_background_tasks(self, app):
        if self.debug:
            print("Starting background tasks...")
        self.running = True
        asyncio.create_task(self.moonraker_client.start())  # Non-blocking task creation

    async def cleanup_background_tasks(self, app):
        if self.debug:
            print("Cleaning up background tasks...")
        self.running = False
        await self.moonraker_client.stop()

def main():
    config_manager = ConfigManager(config_file='test.conf')
    server = SkylightServer(config_manager)
    server.start()

if __name__ == "__main__":
    main()
