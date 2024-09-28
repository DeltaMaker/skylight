import math
import sys
import os
import threading
from skylight.effects_thread import EffectsThread
from skylight.color_utils import ColorUtils
import time
try:
    import neopixel
except ImportError:
    import skylight.neopixel_stub as neopixel

# Add the root directory of your project to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import board
except ImportError:
    import skylight.board_stub as board

class LEDController:
    def __init__(self, led_count=30, led_pin=board.D18, led_brightness=0.25, led_order=neopixel.GRB):
        self.strip = neopixel.NeoPixel(led_pin, led_count, brightness=led_brightness, auto_write=False, pixel_order=led_order)
        self.pixels = [(0, 0, 0)] * led_count
        self.fill_color = (0, 0, 0)
        self.effect_name = None
        self.effects_thread = EffectsThread(update_interval=1/15)
        self.running = False
        self.lock = threading.Lock()
        self.effect_step = 0

        self.data_fields = []
        self.data_values = []
        self.led_count = led_count
        self.brightness = led_brightness

        # Precompute breathe factor for 256 steps
        self.breath_percent = bc = 0.50
        self.num_steps = num = 256
        self.breathe_factors = [1 - (bc/2) + (bc/2) * math.sin(4 * math.pi * i / num) for i in range(num)]
        # Set the default effect to effects_loop
        self.set_effect(self.effects_loop)
        self.set_brightness(led_brightness)

    def add_color(self, name, rgb):
        """Add a new color to the dictionary."""
        ColorUtils.add_color(name, rgb)

    def remove_color(self, name):
        """Remove a color from the dictionary."""
        ColorUtils.remove_color(name)

    def get_color(self, color):
        """Retrieve a named color from the dictionary."""
        return ColorUtils.get_color(color)

    def get_pixels(self):
        with self.lock:
            return self.pixels

    def show_strip(self):
        #with self.lock:
        self.strip.show()
        self.pixels = ColorUtils.scale_pixels(self.pixels, self.brightness)

    def set_data_fields(self, init_data_fields):
        #with self.lock:
        if init_data_fields:
            self.data_fields = []
            self.data_values = []
            start = 0
            for field in init_data_fields:
                mode, value, length, color, bg_color, pad = field
                if isinstance(length, int):
                    mode = "chase" if not isinstance(mode, str) else mode
                    value = self.process_value(value, length, mode)
                    color, bg_color = self.get_color(color), self.get_color(bg_color)
                    pad = 0 if not isinstance(pad, int) else pad
                    start += length + pad
                    if start <= self.led_count:
                        self.data_fields.append((mode, length, color, bg_color, pad))
                        self.data_values.append(value)

    def set_data_values(self, new_values):
        with self.lock:
            for i, value in enumerate(new_values):
                mode, length, _, _, _ = self.data_fields[i]
                self.data_values[i] = self.process_value(value, length, mode)

    def set_brightness(self, brightness):
        with self.lock:
            self.brightness = brightness
            self.strip.brightness = brightness
            self.show_strip()

    def set_color(self, color, index=None):
        color = self.get_color(color)
        scaled_color = ColorUtils.scale_color(color, self.brightness)
        #with self.lock:
        if index is not None and index < self.led_count:
            self.pixels[index] = scaled_color
            self.strip[index] = color
        else:
            self.pixels = [scaled_color] * self.led_count
            self.strip.fill(color)

    def select_color(self, condition, color, bg_color, index):
        self.set_color(color if condition else bg_color, index)

    def clear(self):
        """Clear the LED strip."""
        self.set_color((0, 0, 0))
        self.show_strip()

    def fill(self, color):
        """Fill the LED strip with a specific color."""
        self.set_color(color)
        self.show_strip()

    def start_effects(self, effect_function, **params):
        self.effect_name = effect_function.__name__
        if not self.running:
            self.running = True
            self.effects_thread.set_effect(effect_function, **params)
            self.effects_thread.start()

    def set_effect(self, effect_function, **params):
        with self.lock:
            self.effect_name = effect_function.__name__
            self.effects_thread.set_effect(effect_function, **params)
            if not self.running:
                self.running = True
                self.effects_thread.start()

    def stop_effects(self):
        self.effect_name = None
        self.effects_thread.stop()
        self.running = False
        self.effects_thread.join()

    def stop(self):
        self.stop_effects()

    def get_state(self):
        """Get the current state of the LEDs."""
        return {
            "led_count": self.led_count,
            "color": self.fill_color,
            "brightness": self.brightness,
            "current_effect": self.effect_name
        }

    def effects_loop(self):
        #print ('effects_loop')
        sleep_time = 0.010
        with self.lock:
            for count in range(self.led_count):
                self.effect_step = (self.effect_step + 1) % self.num_steps
                breathe_factor = self.breathe_factors[self.effect_step]
                start = 0
                self.set_color("black")
                for i, value in enumerate(self.data_values):
                    mode, length, color, bg_color, pad = self.data_fields[i]
                    #if mode == 'breathe':
                    #    print(f'breath_factor = {breathe_factor}')
                    progress = int(length * value) if isinstance(value, float) else 0
                    fade_color = ColorUtils.blend_colors(color, bg_color, value) if isinstance(value, float) else color
                    blend_color = ColorUtils.blend_colors(color, bg_color, breathe_factor)
                    breathe_color = ColorUtils.blend_colors((0, 0, 0), color, breathe_factor)
                    breathe_bg_color = ColorUtils.blend_colors((0, 0, 0), bg_color, breathe_factor)
                    for index in range(length):
                        self.apply_mode(mode, self.effect_step, index, length, start+index, progress, color, bg_color, fade_color, blend_color, breathe_color, breathe_bg_color, value)
                    start += length + pad
                self.show_strip()
                time.sleep(sleep_time)

    def apply_mode(self, mode, step, index, length, offset_index, progress, color, bg_color, fade_color, blend_color, breathe_color, breathe_bg_color, value):
        if mode == "chase":
            self.select_color((int(step/3) - index) % length == 0, color, bg_color, offset_index)
        elif mode == "progress":
            self.select_color(progress >= index, color, bg_color, offset_index)
        elif mode == "fade":
            self.set_color(fade_color, offset_index)
        elif mode == "output":
            self.select_color(value[index] == '1', color, bg_color, offset_index)
        elif mode == "blink":
            self.set_color("black" if (step - index) % length == 0 else color, offset_index)
        elif mode == "blend":
            self.select_color(value[index] == '1', blend_color, bg_color, offset_index)
        elif mode == "breathe":
            self.select_color(value[index] == '1', breathe_color, breathe_bg_color, offset_index)
        elif mode == "rainbow":
            # need to be tested
            pos = (index * 256 // self.led_count) + step
            self.set_color(ColorUtils.wheel(pos), offset_index)

    def process_value(self, value, length, mode):
        if isinstance(value, str):
            return value.ljust(length, '0')
        if mode in ['breathe', 'blend']:
            return '1' * length
        if mode == 'count':
            return ('1' * value).ljust(length, '0')
        if isinstance(value, int):
            return bin(value)[2:].zfill(length) if mode == 'binary' else float(value) / 100
        if isinstance(value, float):
            return max(min(value, 1.0), 0.0)
        return value
