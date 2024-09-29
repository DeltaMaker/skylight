import configparser
import os
import pwd
import argparse

class ConfigManager:
    def __init__(self, config_file='skybox.conf', username='pi'):
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self.default_config = {
            'skylight': {
                'skylight_host': 'localhost',
                'skylight_port': '7120',
                'led_count': '30',
                'moonraker_host': 'localhost',
                'moonraker_port': '7125',
                'display_updates': 'True',
                'update_interval': '5',
                'retry_interval': '30',
                'debug': 'False'
            },
            'vision_system': {
                'skycam_host': 'localhost',
                'skycam_port': '7126',
                'camera_input': '0',
                'debug': 'False'
            }
        }
        self.username = username
        self.load_config()

    def skycam_uri(self):
        host = self.get('vision_system', 'skycam_host')
        port = self.getint('vision_system', 'skycam_port')
        return f'ws://{host}:{port}/websocket'

    def moonraker_uri(self):
        host = self.get('skylight', 'moonraker_host')
        port = self.getint('skylight', 'moonraker_port')
        return f'ws://{host}:{port}/websocket'

    @staticmethod
    def parse_arguments():
        parser = argparse.ArgumentParser(description='Run the Skybox Control system.')
        parser.add_argument('-d', '--config-dir', type=str, help='Directory containing the configuration file')
        parser.add_argument('-f', '--config-file', type=str, help='Name of the configuration file')
        #parser.add_argument('-p', '--config-path', type=str, help='Full path to the configuration file')
        args = parser.parse_args()
        return args

    def load_config(self):
        args = self.parse_arguments()
        if args.config_file:
            self.config_file = args.config_file
        if args.config_dir:
            self.config_file = os.path.join(args.config_dir, args.config_file)

        config_exists = os.path.exists(self.config_file)
        if config_exists:
            self.config.read(self.config_file)
        if not config_exists or not all(section in self.config for section in self.default_config):
            self.create_default_config()

    def create_default_config(self):
        for section, settings in self.default_config.items():
            self.config[section] = settings
        with open(self.config_file, 'w') as file:
            self.config.write(file)
        try:
            user_info = pwd.getpwnam(self.username)
            os.chown(self.config_file, user_info.pw_uid, user_info.pw_gid)
        except KeyError:
            print(f"User '{self.username}' does not exist")

    def get(self, section, key, fallback=None):
        return self.config.get(section, key, fallback=fallback)

    def getint(self, section, key, fallback=None):
        return self.config.getint(section, key, fallback=fallback)

    def getboolean(self, section, key, fallback=None):
        return self.config.getboolean(section, key, fallback=fallback)
