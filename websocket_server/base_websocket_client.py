import asyncio
import json
import websockets

class BaseWebSocketClient:
    def __init__(self, connections, subscriptions, debug=True):
        self.connections = connections
        self.subscriptions = subscriptions
        self.debug = debug
        self.current_state = {}
        self.connection_tasks = []
        self.running = False

    async def connect_with_retries(self, uri, root, name):
        """Attempt to connect with retries on failure."""
        retry_interval = 5
        while self.running:
            try:
                async with websockets.connect(uri) as websocket:
                    if self.debug:
                        print(f"Connected to {name}: {uri}")
                    await self.subscribe(websocket, name)
                    await self.listen(websocket, root, name)
            except (websockets.ConnectionClosedError, websockets.InvalidURI, websockets.InvalidHandshake) as e:
                if self.debug:
                    print(f"Connection to {name} failed: {e}. Retrying in {retry_interval} seconds...")
                await asyncio.sleep(retry_interval)
            except (ConnectionRefusedError, OSError) as e:
                if self.debug:
                    print(f"Connection to {name} failed: {e}. Retrying in {retry_interval} seconds...")
                await asyncio.sleep(retry_interval)
            except Exception as e:
                if self.debug:
                    print(f"Unexpected error while connecting to {name}: {e}")
                await asyncio.sleep(retry_interval)

    async def subscribe(self, websocket, name):
        subscribe_command = self.subscriptions[name]
        await websocket.send(json.dumps(subscribe_command))
        if self.debug:
            print(f"Subscribed to {name}")

    async def listen(self, websocket, root, name):
        while self.running:
            try:
                message = await websocket.recv()
                data = json.loads(message)
                if 'method' in data and data['method'].endswith('update'):
                    await self.update_state(data['params'][0], root)
                elif 'result' in data and 'status' in data['result']:
                    await self.update_state(data['result']['status'], root)
                    pass
                else:
                    if self.debug:
                        pass  # Handle other cases or log them if needed
            except websockets.ConnectionClosed:
                if self.debug:
                    print(f"Connection to {name} closed")
                break
            except Exception as e:
                if self.debug:
                    print(f"Error while listening to {name}: {e}")
                break

    async def update_state(self, updated_objects, root):
        """Update the state dictionary with the objects that have changed."""
        if root not in self.current_state:
            self.current_state[root] = {}
        self._deep_update(self.current_state[root], updated_objects)
        await self.on_state_update(root, updated_objects)

    def _deep_update(self, state, updates):
        try:
            for key, value in updates.items():
                if isinstance(value, dict):
                    if key not in state or not isinstance(state[key], dict):
                        state[key] = {}
                    self._deep_update(state[key], value)
                else:
                    state[key] = value
        except Exception as e:
            if self.debug:
                print(f'_deep_update error: {e}')

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

    async def on_state_update(self, root, updated_objects):
        """Hook method for handling state updates."""
        if self.debug:
            print(f"Updated state for {root}: {json.dumps(self.current_state[root], indent=2)}")
        pass

    async def run_connections(self):
        for connection in self.connections:
            for root, uri in connection.items():
                task = asyncio.create_task(self.connect_with_retries(uri, root, root))
                self.connection_tasks.append(task)
        await asyncio.gather(*self.connection_tasks)

    async def start(self):
        if self.debug:
            print("Starting client connections...")
        self.running = True
        await self.run_connections()

    async def stop(self):
        self.running = False
        for task in self.connection_tasks:
            task.cancel()
        await asyncio.gather(*self.connection_tasks, return_exceptions=True)
        self.connection_tasks.clear()

    def get_current_state(self):
        return self.current_state

# Example usage
def main():
    connections = [
        {"moonraker": "ws://localhost:7125/websocket"}
    ]
    subscriptions = {
        "moonraker": {
            "jsonrpc": "2.0",
            "method": "printer.objects.subscribe",
            "params": {
                "objects": {
                    "print_stat": None,
                    "display_status": None,
                    "idle_timeout": None,
                    "extruder": ['temperature', 'target', 'power']
                }
            },
            "id": 2
        }
    }
    client = BaseWebSocketClient(connections, subscriptions, debug=True)
    asyncio.run(client.start())

if __name__ == "__main__":
    main()
