import argparse
import json
from pathlib import Path
from time import time, sleep
import concurrent.futures
from redfish import redfish_client


REDFISH_BASE = '/redfish/v1'
HTTP_OK_200 = 200


class Collector:
    def __init__(self, bmc_hostname, bmc_username, bmc_password):
        """Sets up the bmc client - DOES NOT save the credentials"""
        bmc_url = f"https://{bmc_hostname}"
        print(f"Connecting to {bmc_url} ...")
        self.bmc = redfish_client(bmc_url, bmc_username, bmc_password)
        print("... connected")
        self.boards = {}
        self.bmc.login(auth="session")
        print("Logged in")

        self.init_boards()

    def init_boards(self):
        self.motherboard_path = None
        chassis_path = REDFISH_BASE + "/Chassis"
        response = self.bmc.get(chassis_path)
        if response.status == HTTP_OK_200:
            response_data = json.loads(response.text)
            paths = [member["@odata.id"] for member in response_data["Members"]]
            for path in paths:
                ending = path.split("/")[-1]
                if ending.lower() in {"motherboard", "self", "gpu_board"}:
                    self.boards[path] = {
                        'power': {}
                    }

    def sample_power(self, runtime_secs=300, sample_hz=1):
        start_time = time()
        while time() < start_time + runtime_secs:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                # Start the load operations and mark each future with its board_path
                future_to_path = {
                    executor.submit(self.get_power, path): path for path in self.boards
                }
                for future in concurrent.futures.as_completed(future_to_path):
                    path = future_to_path[future]
                    try:
                        power = future.result()
                    except Exception as e:
                        print(f"{path} generated an exception: {e}")
                    else:
                        time_delta = time() - start_time
                        self.boards[path]['power'][time_delta] = power
                        print(f"{time_delta:.1f>8}{path:<20}: {power:.1f} Watts")

            sleep(1/sample_hz)

    def get_power(self, board_path):
        data = self._redfish_get(f"{board_path}/Power")
        return data.get("PowerControl", [{}])[0].get("PowerConsumedWatts")

    def _redfish_get(self, path):
        response = self.bmc.get(path)
        if response.status == HTTP_OK_200:
            return json.loads(response.text)
        return None

    def plot_power(self, save_file=None):
        pass

    # def __del__(self):
    #     try:
    #         self.bmc.logout()
    #     except Exception:
    #         pass


if __name__ == "__main__":

    def parse_cli():
        parser = argparse.ArgumentParser(
            description='Tool to collect power data from Redfish BMC'
        )

        parser.add_argument('--bmc_hostname', type=str,
                            help='The hostname of the bmc')

        parser.add_argument('--bmc_username', type=str,
                            help='The bmc user/login name')

        parser.add_argument('--bmc_password', type=str,
                            help='Password for the bmc user')

        return parser.parse_args()

    args = parse_cli()
    collector = Collector(
        args.bmc_hostname,
        args.bmc_username,
        args.bmc_password
    )
    collector.sample_power(10, 1)
    for board in collector.boards:
        boardname = Path(board).name
        print(boardname)
        print("\t", collector.boards[board]['power'])
