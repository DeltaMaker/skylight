import json
import time
import asyncio
from aiohttp import web

class BaseWebSocketServer:
    def __init__(self, host='0.0.0.0', port=8080, debug=False):
        self.host = host
        self.port = port
        self.debug = debug
        self.running = False
        self.subscribers = set()
        self.loop = None
        self.current_state = {}
        self.last_sent_state = {}

        if self.debug:
            print(f"Initialized BaseWebSocketServer with host={self.host}, port={self.port}")

    def get_state(self, path, default=None):
        """Get the value from self.current_state specified by the path."""
        keys = path.split('.')
        current_dict = self.current_state
        for key in keys:
            if isinstance(current_dict, dict) and key in current_dict:
                current_dict = current_dict[key]
            else:
                return default
        if default is not None and type(default) != type(current_dict):
            print(f'get_state() type mismatch {type(default)} {type(current_dict)}')
        return current_dict

    async def broadcast_state_update(self, new_state):
        """Broadcast the server state to all subscribers if there are changes."""
        changed_objects = self.detect_changes(new_state)
        if not changed_objects:
            if self.debug:
                #print(f"No changed objects detected in new_state: {new_state}")
                pass
            return

        for ws, sub_id, requested_paths in self.subscribers:
            if self.has_requested_objects_changed(requested_paths, changed_objects):
                requested_objects = {path: self.get_nested_value(self.current_state, path.split('.')) for path in requested_paths}
                response_params = self.extract_state_params(requested_objects)
                response = {
                    "jsonrpc": "2.0",
                    "method": "notify_status_update",
                    "params": [response_params, time.time()],
                    "id": sub_id
                }
                try:
                    message = json.dumps(response)
                    if self.debug:
                        print(f"Broadcasting state update to subscriber {sub_id} with params {response_params}")
                    await ws.send_str(message)
                    self.update_last_sent_state(ws, requested_paths, response_params)
                except Exception as e:
                    if self.debug:
                        print(f'Error broadcasting state update: {e}')

    def detect_changes_(self, new_state):
        """Detect changes between the new state and the current state."""
        changed_objects = set()
        if self.debug:
            print("detect changes in ", new_state)
        for key, value in new_state.items():
            if key not in self.current_state or self.current_state[key] != value:
                changed_objects.add(key)
        self.current_state.update(new_state)
        if self.debug:
            print("changed object set ", changed_objects)
        return changed_objects

    def detect_changes(self, new_state):
        changes = self.deep_compare(self.current_state, new_state)
        if changes:
            self.current_state = new_state
            self.broadcast_changes(changes)
        return changes
    def deep_compare(self, old, new, path=""):
        changes = {}
        for key in old.keys() | new.keys():
            if key in old and key in new:
                if isinstance(old[key], dict) and isinstance(new[key], dict):
                    nested_changes = self.deep_compare(old[key], new[key], path + f".{key}")
                    if nested_changes:
                        changes[key] = nested_changes
                elif old[key] != new[key]:
                    changes[key] = (old[key], new[key])
            elif key in old:
                changes[key] = (old[key], None)
            else:
                changes[key] = (None, new[key])
        return changes

    def broadcast_changes(self, changes):
        for ws, sub_id, paths in self.subscribers:
            updated_paths = {path: self.get_nested_value(changes, path.split('.')) for path in paths if self.get_nested_value(changes, path.split('.')) is not None}
            if updated_paths:
                message = {
                    "jsonrpc": "2.0",
                    "method": "notify_status_update",
                    "params": [updated_paths, time.time()],
                    "id": sub_id
                }
                asyncio.create_task(ws.send_str(json.dumps(message)))
                self.update_last_sent_state(ws, paths, updated_paths)

    def get_nested_value(self, data, path):
        for key in path:
            if isinstance(data, dict):
                data = data.get(key)
            else:
                return None
        return data

    def update_last_sent_state(self, ws, paths, state):
        for path in paths:
            self.last_sent_state[ws][path] = self.get_nested_value(state, path.split('.'))

    def has_requested_objects_changed(self, requested_objects, changed_objects):
        """Check if any of the requested objects have changed."""
        return any(obj in changed_objects for obj in requested_objects)

    def extract_state_params(self, requested_objects):
        """Extract the parameters from the state based on requested objects."""
        if self.debug:
            print(f"Extracting parameters for requested objects: {requested_objects}")
        #return {key: value for key, value in requested_objects.items() if value is not None}
        return {key: self.current_state[key] for key in requested_objects if key in self.current_state}

    def update_last_sent_state(self, ws, requested_objects, state_params):
        """Update the last sent state for a subscriber."""
        self.last_sent_state[ws] = {obj: state_params[obj] for obj in requested_objects if obj in state_params}

    async def websocket_handler(self, request):
        """Handle incoming WebSocket connections and requests."""
        if self.debug:
            print(f"Handling new WebSocket connection from {request.remote}")
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    request = json.loads(msg.data)
                    if self.debug:
                        print(f"Received message: {request}")

                    if await self.process_custom_methods(request, ws, msg):
                        continue

                    if 'method' in request:
                        if request['method'].endswith('subscribe'):
                            sub_id = request.get('id')
                            requested_objects = request.get('params').get('objects', {})
                            requested_paths = frozenset(self.get_all_paths(requested_objects))
                            self.subscribers.add((ws, sub_id, requested_paths))
                            if self.debug:
                                print(f"Subscription request received: id={sub_id}, params={request.get('params')}")
                            await ws.send_str(json.dumps({"jsonrpc": "2.0", "result": {}, "id": sub_id}))

                            # Send the current state immediately
                            initial_state = {path: self.get_nested_value(self.current_state, path.split('.')) for path in requested_paths}
                            initial_response = {
                                "jsonrpc": "2.0",
                                "method": "notify_status_update",
                                "params": [initial_state, time.time()],
                                "id": sub_id
                            }
                            await ws.send_str(json.dumps(initial_response))
                            self.update_last_sent_state(ws, requested_paths, initial_state)

                        elif request['method'].endswith('query'):
                            requested_paths = self.get_all_paths(request.get('params', {}).get('objects', {}))
                            response_data = {
                                "status": {path: self.get_nested_value(self.current_state, path.split('.')) for path in requested_paths}
                            }
                            response = {
                                "jsonrpc": "2.0",
                                "result": response_data,
                                "id": request["id"]
                            }
                            if self.debug:
                                print(f"Query request received: id={request['id']}, params={request.get('params')}")
                            await ws.send_str(json.dumps(response))
                elif msg.type == web.WSMsgType.ERROR:
                    if self.debug:
                        print(f'WebSocket connection closed with exception {ws.exception()}')
        except Exception as e:
            if self.debug:
                print(f'WebSocket error: {e}')
        finally:
            self.subscribers = {(subscriber_ws, subscriber_id, requested_paths) for
                                subscriber_ws, subscriber_id, requested_paths in self.subscribers if
                                subscriber_ws != ws}
            if self.debug and 'remote' in request:
                print(f"WebSocket connection from {request.remote} closed.")
            await ws.close()
        return ws

    async def handle_http_request(self, request):
        """Handle incoming HTTP GET requests."""
        query_params = request.query_string.split('&')
        requested_objects = set(param.split('=')[0] for param in query_params)
        response_data = {"result": {"status": self.get_response_params(requested_objects)}}
        return web.json_response(response_data)

    def get_response_params(self, requested_objects):
        """Get the response parameters based on the requested objects. To be overridden by subclasses."""
        #return {}
        return self.extract_state_params(requested_objects)

    def get_all_paths(self, obj, parent_key='', sep='.'):
        """Get all paths from a nested dictionary, supporting wildcard."""
        paths = []
        for k, v in obj.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if v == '*':
                sub_paths = self.get_all_paths(self.get_nested_value(self.current_state, new_key.split(sep)), new_key, sep=sep)
                paths.extend(sub_paths)
            elif isinstance(v, list):
                for sub_key in v:
                    paths.append(f"{new_key}{sep}{sub_key}")
            elif isinstance(v, dict):
                paths.extend(self.get_all_paths(v, new_key, sep=sep))
            else:
                paths.append(new_key)
        return paths

    def get_nested_value_(self, data_dict, keys):
        """Get a nested value from a dictionary."""
        for key in keys:
            data_dict = data_dict.get(key, None)
            if data_dict is None:
                return None
        return data_dict

    async def start_server(self):
        """Start the HTTP and WebSocket server."""
        if self.debug:
            print(f"Starting server at {self.host}:{self.port}")
        app = web.Application()
        app.router.add_get('/websocket', self.websocket_handler)
        app.router.add_get('/printer/objects/query', self.handle_http_request)  # Add custom HTTP route
        self.add_custom_routes(app.router)

        app.on_startup.append(self.start_background_tasks)
        app.on_cleanup.append(self.cleanup_background_tasks)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host=self.host, port=self.port)
        await site.start()

        while self.running:
            if self.debug:
                print("Server is running...")
            await asyncio.sleep(30)  # Keep running

    async def start_background_tasks(self, app):
        if self.debug:
            print("Starting background tasks...")
        self.running = True

    async def cleanup_background_tasks(self, app):
        if self.debug:
            print("Cleaning up background tasks...")
        self.running = False

    def start(self):
        if self.debug:
            print("Starting event loop...")
        self.loop = asyncio.get_event_loop()
        self.loop.run_until_complete(self.start_server())

    def stop(self):
        if self.debug:
            print("Stopping event loop...")
        self.running = False
        self.loop.stop()

    async def process_custom_methods(self, request, ws, msg):
        """Hook method for processing custom methods in derived classes."""
        return False

    def add_custom_routes(self, router):
        """Hook method for adding custom routes in derived classes."""
        #router.add_route('*', '/{tail:.*}', self.handle_custom_route)
        pass

    async def handle_custom_route(self, request):
        return web.Response(status=404, text=f"{request.path} not found.")
