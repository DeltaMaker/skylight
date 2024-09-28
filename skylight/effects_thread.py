import threading
import time

class EffectsThread(threading.Thread):
    def __init__(self, update_interval=0.1):
        super().__init__()
        self.update_interval = update_interval
        self.effect_function = None
        self.effect_params = {}
        self.running = False

    def run(self):
        while self.running:
            if self.effect_function:
                self.effect_function(**self.effect_params)
            time.sleep(self.update_interval)

    def set_effect(self, effect_function, **params):
        self.effect_function = effect_function
        self.effect_params = params

    def start(self):
        self.running = True
        super().start()

    def stop(self):
        self.running = False
        self.join()
