import os.path
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

import atlassian.errors
import pandas as pd
import matplotlib.colors as mc
import matplotlib.pyplot as plt
import numpy as np
from src.common import ConfluenceConnection, ConfluenceNodeMapper


class DataManager:
    """
    This class downloads attachments from Confluence and filters them for the needed attachments,
    as the Confluence API does not support single downloading of attachments. The correct attachment
    will be stored in a file system, and the remaining attachments will be deleted.
    """

    def __init__(self, confluence: ConfluenceConnection):
        self.__confluence = confluence
        self.generic_attachment_save_path = os.path.join(os.getenv('DIR.RESOURCES'),
                                                         'download')  # Temporary working file
        self.correct_attachment_save_path = os.path.join(os.getenv('DIR.RESOURCES'), 'stats')  # Permanent storage path
        self.__ensure_directory_exists(self.correct_attachment_save_path)

    def __del__(self):
        self.__delete_directory(self.correct_attachment_save_path)

    def get_stat_file_from_page(self, page_id: str, filename: str):
        """
        Downloads all available files from the page with the specified ID in Confluence.
        The needed stats file will be moved to a permanent directory, and the temporary directory will be deleted.
        """
        self.__ensure_directory_exists(self.generic_attachment_save_path)
        try:
            self.__confluence.download_attachments_from_page(page_id, path=self.generic_attachment_save_path)
            src = os.path.join(self.generic_attachment_save_path, filename)
            dest = os.path.join(self.correct_attachment_save_path, filename)
            moved_file = self.__move_file(src, dest)
            self.__delete_directory(self.generic_attachment_save_path)
            return moved_file
        except atlassian.errors.ApiError:
            print(f"Error downloading attachments for page ID: {page_id}")
            return None

    def __move_file(self, src: str, dest: str):
        """
        Moves files from a source to a destination path. Catches exceptions to allow the program to continue running.
        """
        try:
            shutil.move(src, dest)
            return dest
        except Exception as e:
            print(f"Exception: Could not move file from {src} to {dest}. Error: {e}")
            return None

    def __delete_directory(self, dir_path: str):
        """
        Deletes the specified directory if it exists.
        """
        if os.path.exists(dir_path) and os.path.isdir(dir_path):
            shutil.rmtree(dir_path)
        else:
            print(f"Directory does not exist: {dir_path}")

    def __ensure_directory_exists(self, dir_path: str):
        """
        Ensures that the specified directory exists, creating it if necessary.
        """
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)


class HeatMapFactory:
    def plot(self, data: dict, dates: list):
        sorted_data = self._order_dict(data)
        clinics = list(sorted_data.keys())
        data_matrix = np.array(list(sorted_data.values()))

        # Define the colors and thresholds (absolute values)
        colors = [
            'black',
            'mediumblue',
            'yellow',
            'yellow',
            'red'
        ]
        no_imp = -10
        zero = 0
        low_err = 1
        high_err = 5
        extr_err = 10
        bounds = [no_imp, zero, low_err, high_err, extr_err, extr_err*2]

        # Create the heatmap with its configurations
        cmap = mc.ListedColormap(colors)
        norm = mc.BoundaryNorm(bounds, cmap.N)
        plt.figure(figsize=(data_matrix.shape[1] / 3, data_matrix.shape[0] / 4))
        extent = (0, data_matrix.shape[1], 0, data_matrix.shape[0])
        plt.imshow(data_matrix, cmap=cmap, norm=norm, aspect="auto", extent=extent)
        cbar = plt.colorbar(label="Error Rate in %")
        cbar.set_ticklabels(ticklabels=["No Imports", f'{zero}, Online', f'{low_err}, Low error rate', f'{high_err}, High error rate', f'{extr_err}, Extreme error rate', ''])
        plt.subplots_adjust(left=0.2)

        # Create horizontal lines and clinic labels for y axis
        ticks = np.arange(len(data_matrix))
        plt.hlines(ticks, xmin=0, xmax=data_matrix.shape[1], color='grey', linewidth=0.5)
        label_ticks = ticks + 0.5
        plt.yticks(ticks=label_ticks, labels=clinics[::-1], fontsize=8)
        plt.xticks(ticks=np.arange(len(dates)), labels=dates, rotation=90, ha="left", fontsize=8)
        plt.savefig('heatmap.png')

    def _order_dict(self, data: dict):
        last_week_modifier = 6  # Factor by which the values from last week are multiplied by
        sorted_data = dict(
            sorted(
                data.items(),
                key=lambda item: sum(item[1][:-7]) + sum(x * last_week_modifier for x in item[1][-7:]) if len(
                    item[1]) > 7 else sum(
                    item[1]),
                reverse=True
            )
        )
        return sorted_data


class ChartManager:
    def __init__(self, mapper: ConfluenceNodeMapper, csv_paths: list = None,
                 save_path: str = "error_rates_histogram.png", max_days: int = 42):
        self.mapper = mapper
        self.csv_paths = csv_paths if csv_paths is not None else []
        self.save_path = save_path
        self.max_days = max_days

    def heat_map(self):
        """
        This method manages the collection of needed error rate data and initializes the Heatmap generation factory.
        """
        hm = HeatMapFactory()
        data = {}

        def process_path(path):
            try:
                dates, error_rates = Helper.read_error_rates(path)
                error_rates = error_rates[-self.max_days:]
                dates = dates[-self.max_days:]

                clinic_id = Helper.get_clinic_num(path)
                clinic_name = self.mapper.get_node_value_from_mapping_dict(clinic_id, "COMMON_NAME")
                data[clinic_name] = error_rates
                return data, dates
            except Exception as e:
                print(f"Error processing {path}: {e}")
                return None

        with ThreadPoolExecutor() as executor:
            futures = {executor.submit(process_path, path): path for path in self.csv_paths}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    data, dates = result

        hm.plot(data, dates)
        plt.savefig(self.save_path)


class Helper:
    @staticmethod
    def get_clinic_num(path: str):
        """
        Returns a clinic number contained in a given path. Required syntax: .../{clinic num}_...
        """
        num = path.split('/')[-1].split("_")[0]
        return num

    @staticmethod
    def read_error_rates(csv_file):
        """
        This method extracts error rates and date information from their respective columns in a csv file. Empty error
        rates will be marked with a negative value
        """
        _error_rates_df = []

        _df = pd.read_csv(csv_file, sep=';')
        try:
            _df['date'] = pd.to_datetime(_df['date'], format='%Y-%m-%d %H:%M:%S.%f%z')
        except Exception as e:
            print(f'fixing error: {e}')
            _df = pd.read_csv(csv_file, sep=',')
            _df['date'] = pd.to_datetime(_df['date'], format='%Y-%m-%d %H:%M:%S.%f%z')
        _df = _df.sort_values(by='date')
        _date = [x.strftime('%d-%m') for x in _df['date']]

        _df[_df == '-'] = -1.0
        _df['daily_error_rate'] = _df['daily_error_rate'].apply(lambda x: float(x))
        _error_rates = _df['daily_error_rate'].to_numpy()

        return _date, _error_rates