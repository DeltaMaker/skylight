def clamp(value, min_value=0, max_value=255):
    return max(min_value, min(max_value, int(value)))

class ColorUtils:
    colors = {
        "black": (0, 0, 0),
        "gray": (127, 127, 127),
        "white": (255, 255, 255),
        "red": (255, 0, 0),
        "green": (0, 255, 0),
        "blue": (0, 0, 255),
        "cyan": (0, 255, 255),
        "magenta": (255, 0, 255),
        "yellow": (255, 255, 0),
    }

    @staticmethod
    def add_color(name, rgb):
        """Add a new color to the dictionary."""
        ColorUtils.colors[name] = rgb

    @staticmethod
    def remove_color(name):
        """Remove a color from the dictionary."""
        if name in ColorUtils.colors:
            del ColorUtils.colors[name]

    @staticmethod
    def get_color(color):
        """Retrieve a named color from the dictionary."""
        if isinstance(color, str):
            scale = 1.0
            if color.startswith('dark-'):
                color = color[5:]
                scale = 0.5
            elif color.startswith('bright-'):
                color = color[7:]
                scale = 1.25
            else:
                return ColorUtils.colors.get(color, (0, 0, 0))
            return ColorUtils.scale_color(ColorUtils.colors.get(color, (0, 0, 0)), scale)
        return color

    @staticmethod
    def scale_color(color, factor):
        r, g, b = color
        return clamp(r * factor), clamp(g * factor), clamp(b * factor)

    @staticmethod
    def blend_colors(c1, c2, f2=0.5):
        f1 = 1 - f2
        r1, g1, b1 = c1
        r2, g2, b2 = c2
        return clamp(r1*f1 + r2*f2), clamp(g1*f1 + g2*f2), clamp(b1*f1 + b2*f2)

    @staticmethod
    def wheel(pos):
        pos %= 255
        if pos < 85:
            return pos * 3, 255 - pos * 3, 0
        elif pos < 170:
            pos -= 85
            return 255 - pos * 3, 0, pos * 3
        else:
            pos -= 170
            return 0, pos * 3, 255 - pos * 3

    @staticmethod
    def scale_pixels(pixels, factor):
        return [(clamp(r * factor), clamp(g * factor), clamp(b * factor)) for r, g, b in pixels]
