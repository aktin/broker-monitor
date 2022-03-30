# -*- coding: utf-8 -*
# Created on Tue Mar 22 12:00 2022
# @version: 1.0

#
#      Copyright (c) 2022  Alexander Kombeiz
#
#      This program is free software: you can redistribute it and/or modify
#      it under the terms of the GNU Affero General Public License as
#      published by the Free Software Foundation, either version 3 of the
#      License, or (at your option) any later version.
#
#      This program is distributed in the hope that it will be useful,
#      but WITHOUT ANY WARRANTY; without even the implied warranty of
#      MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#      GNU Affero General Public License for more details.
#
#      You should have received a copy of the GNU Affero General Public License
#      along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
#

import json
import logging
import os
import sys
from abc import ABC, abstractmethod
from datetime import datetime
from datetime import timedelta

import bs4
from bs4.element import Tag

from common import ConfluenceConnection
from common import ConfluenceNodeMapper
from common import CSVHandler
from common import InfoCSVHandler
from common import ErrorCSVHandler
from common import SingletonMeta
from common import __init_logger
from common import __stop_logger
from common import load_properties_file_as_environment


class TemplatePageContentWriter(ABC):
    _PAGE_TEMPLATE: bs4.BeautifulSoup = None

    def add_content_to_template_page(self, page_template: str) -> str:
        self._load_template_page_into_memory(page_template)
        self._add_content_to_template_soup()
        return str(self._PAGE_TEMPLATE)

    def _load_template_page_into_memory(self, page_template: str):
        self._PAGE_TEMPLATE = bs4.BeautifulSoup(page_template, 'html.parser')

    @abstractmethod
    def _add_content_to_template_soup(self):
        pass


class TemplatePageCSVWriter:
    _CSV_HANDLER: CSVHandler

    def __init__(self, id_node: str, dir_working=''):
        name_csv = self._CSV_HANDLER.generate_csv_name(id_node)
        path_csv = os.path.join(dir_working, name_csv)
        self._DF = self._CSV_HANDLER.read_csv_as_df(path_csv)


class TemplatePageCSVInfoWriter(TemplatePageCSVWriter, TemplatePageContentWriter):
    _CSV_HANDLER = InfoCSVHandler()

    def _add_content_to_template_soup(self):
        self.__add_dates_to_template_soup()
        self.__add_total_imports_to_template_soup()
        self.__add_daily_imports_to_template_soup()

    def __add_dates_to_template_soup(self):
        dict_last_row = self._DF.iloc[-1].to_dict()
        self._PAGE_TEMPLATE.find(class_='last_check').string.replace_with(dict_last_row.get('date'))
        self._PAGE_TEMPLATE.find(class_='last_contact').string.replace_with(dict_last_row.get('last_contact'))
        self._PAGE_TEMPLATE.find(class_='last_start').string.replace_with(dict_last_row.get('last_start'))
        self._PAGE_TEMPLATE.find(class_='last_write').string.replace_with(dict_last_row.get('last_write'))
        self._PAGE_TEMPLATE.find(class_='last_reject').string.replace_with(dict_last_row.get('last_reject'))

    def __add_total_imports_to_template_soup(self):
        dict_last_row = self._DF.iloc[-1].to_dict()
        self._PAGE_TEMPLATE.find(class_='imported').string.replace_with(dict_last_row.get('imported'))
        self._PAGE_TEMPLATE.find(class_='updated').string.replace_with(dict_last_row.get('updated'))
        self._PAGE_TEMPLATE.find(class_='invalid').string.replace_with(dict_last_row.get('invalid'))
        self._PAGE_TEMPLATE.find(class_='failed').string.replace_with(dict_last_row.get('failed'))
        self._PAGE_TEMPLATE.find(class_='error_rate').string.replace_with(dict_last_row.get('error_rate'))

    def __add_daily_imports_to_template_soup(self):
        dict_last_row = self._DF.iloc[-1].to_dict()
        self._PAGE_TEMPLATE.find(class_='daily_imported').string.replace_with(dict_last_row.get('daily_imported'))
        self._PAGE_TEMPLATE.find(class_='daily_updated').string.replace_with(dict_last_row.get('daily_updated'))
        self._PAGE_TEMPLATE.find(class_='daily_invalid').string.replace_with(dict_last_row.get('daily_invalid'))
        self._PAGE_TEMPLATE.find(class_='daily_failed').string.replace_with(dict_last_row.get('daily_failed'))
        self._PAGE_TEMPLATE.find(class_='daily_error_rate').string.replace_with(dict_last_row.get('daily_error_rate'))


class TemplatePageCSVErrorWriter(TemplatePageCSVWriter, TemplatePageContentWriter):
    _CSV_HANDLER = ErrorCSVHandler()
    __NUM_ERRORS: int = 20

    def _add_content_to_template_soup(self):
        table_errors = self.__create_confluence_error_table()
        self._PAGE_TEMPLATE.find(class_='table_errors_body').replace_with(table_errors)

    def __create_confluence_error_table(self) -> Tag:
        list_dicts_error = self._DF.head(self.__NUM_ERRORS).to_dict('records')
        list_error_rows = []
        for dict_error in list_dicts_error:
            error_row = self.__create_error_table_row(dict_error['timestamp'], dict_error['repeats'], dict_error['content'])
            list_error_rows.append(error_row)
        table_errors = self.__generate_error_table_frame()
        table_errors.find('tbody').extend(list_error_rows)
        return table_errors

    def __generate_error_table_frame(self) -> bs4.BeautifulSoup:
        header_timestamp = self.__create_table_header_tag('timestamp')
        header_repeats = self.__create_table_header_tag('repeats')
        header_content = self.__create_table_header_tag('content')
        row_header = bs4.BeautifulSoup().new_tag('tr')
        row_header.extend([header_timestamp, header_repeats, header_content])
        table_errors = bs4.BeautifulSoup().new_tag('tbody', attrs={'class': 'table_errors_body'})
        table_errors.extend(row_header)
        table_errors = bs4.BeautifulSoup(str(table_errors), 'html.parser')
        return table_errors

    @staticmethod
    def __create_table_header_tag(content: str) -> Tag:
        tag = bs4.BeautifulSoup().new_tag('th', attrs={'style': 'text-align: center;'})
        tag.append(content)
        return tag

    def __create_error_table_row(self, timestamp: str, repeats: str, content: str) -> Tag:
        column_timestamp = self.__create_table_row_tag(timestamp, centered=True)
        column_repeats = self.__create_table_row_tag(repeats, centered=True)
        column_content = self.__create_table_row_tag(content)
        row_error = bs4.BeautifulSoup().new_tag('tr')
        row_error.extend([column_timestamp, column_repeats, column_content])
        return row_error

    @staticmethod
    def __create_table_row_tag(content: str, centered=False) -> Tag:
        attribute = {'style': 'text-align: center;'} if centered is True else {}
        tag = bs4.BeautifulSoup().new_tag('td', attrs=attribute)
        tag.append(content)
        return tag


class TemplatePageNodeResourceWriter(TemplatePageContentWriter):

    def __init__(self, id_node: str, dir_working=''):
        self.__ID_NODE = id_node
        self.__DIR_WORKING = dir_working

    def _add_content_to_template_soup(self):
        self.__add_versions_to_template_soup()
        self.__add_rscript_to_template_soup()
        self.__add_python_to_template_soup()
        self.__add_import_scripts_to_template_soup()

    def __add_versions_to_template_soup(self):
        versions = self.__load_node_resource_as_dict('versions')
        self._PAGE_TEMPLATE.find(class_='os').string.replace_with(self.__get_value_of_dict(versions, 'os'))
        self._PAGE_TEMPLATE.find(class_='kernel').string.replace_with(self.__get_value_of_dict(versions, 'kernel'))
        self._PAGE_TEMPLATE.find(class_='java').string.replace_with(self.__get_value_of_dict(versions, 'java'))
        self._PAGE_TEMPLATE.find(class_='wildfly').string.replace_with(self.__get_value_of_dict(versions, 'j2ee-impl'))
        self._PAGE_TEMPLATE.find(class_='apache2').string.replace_with(self.__get_value_of_dict(versions, 'apache2'))
        self._PAGE_TEMPLATE.find(class_='postgresql').string.replace_with(self.__get_value_of_dict(versions, 'postgres'))
        self._PAGE_TEMPLATE.find(class_='api').string.replace_with(self.__get_value_of_dict(versions, 'dwh-api'))
        self._PAGE_TEMPLATE.find(class_='dwh').string.replace_with(self.__get_value_of_dict(versions, 'dwh-j2ee'))

    def __load_node_resource_as_dict(self, name_resource: str) -> dict:
        name_file = ''.join([self.__ID_NODE, '_', name_resource, '.txt'])
        path_file = os.path.join(self.__DIR_WORKING, name_file)
        if not os.path.exists(path_file):
            return {}
        with open(path_file) as file:
            resource = json.load(file)
        return resource

    @staticmethod
    def __get_value_of_dict(dictionary: dict, key: str) -> str:
        if key not in dictionary:
            return '-'
        return dictionary[key]

    def __add_rscript_to_template_soup(self):
        dict_rscript = self.__load_node_resource_as_dict('rscript')
        rscript = self.__concat_dict_items_as_string(dict_rscript)
        self._PAGE_TEMPLATE.find(class_='rscript').string.replace_with(rscript)

    @staticmethod
    def __concat_dict_items_as_string(dictionary: dict) -> str:
        tmp_list = []
        if not dictionary:
            return '-'
        for key, value in dictionary.items():
            value = '?' if value is None else value
            item = ''.join([key, ' ', '(', value, ')'])
            tmp_list.append(item)
        return ', '.join(tmp_list)

    def __add_python_to_template_soup(self):
        dict_python = self.__load_node_resource_as_dict('python')
        python = self.__concat_dict_items_as_string(dict_python)
        self._PAGE_TEMPLATE.find(class_='python').string.replace_with(python)

    def __add_import_scripts_to_template_soup(self):
        dict_import_scripts = self.__load_node_resource_as_dict('import-scripts')
        import_scripts = self.__concat_dict_items_as_string(dict_import_scripts)
        self._PAGE_TEMPLATE.find(class_='import_scripts').string.replace_with(import_scripts)


class TemplatePageStatusChecker(TemplatePageContentWriter):
    __WITDH_IMPORT_THRESHOLD: float = 0.33

    def __init__(self, id_node: str):
        mapper = ConfluenceNodeMapper()
        self.__DAILY_IMPORT_TRESHOLD = mapper.get_node_value_from_mapping_dict(id_node, 'DAILY_IMPORT_THRESHOLD')

    def _add_content_to_template_soup(self):
        if self.__is_template_soup_offline():
            status = self.__create_status_element('OFFLINE', 'Red')
        elif self.__is_template_soup_not_importing():
            status = self.__create_status_element('NO IMPORTS', 'Red')
        elif self.__are_template_soup_imports_deviating():
            status = self.__create_status_element('DEVIATING IMPORTS', 'Yellow')
        elif self.__is_template_soup_daily_error_rate_above_one():
            status = self.__create_status_element('HIGH ERROR RATE', 'Yellow')
        else:
            status = self.__create_status_element('ONLINE', 'GREEN')
        self._PAGE_TEMPLATE.find(class_='status').replace_with(status)

    def __is_template_soup_offline(self) -> bool:
        last_contact = self._PAGE_TEMPLATE.find(class_='last_contact').string
        return self.__is_date_longer_ago_than_yesterday(last_contact)

    def __create_status_element(self, title: str, color: str) -> Tag:
        param_title = self.__create_ac_parameter_tag('title', title)
        param_color = self.__create_ac_parameter_tag('color', color)
        frame = self.__create_ac_macro_tag('status')
        frame.extend([param_title, param_color])
        status = bs4.BeautifulSoup().new_tag('td', attrs={'style': 'text-align:center;', 'class': 'status'})
        status.append(frame)
        return status

    @staticmethod
    def __create_ac_parameter_tag(name: str, content: str) -> Tag:
        parameter = bs4.BeautifulSoup().new_tag('ac:parameter', attrs={'ac:name': name})
        parameter.append(content)
        return parameter

    @staticmethod
    def __create_ac_macro_tag(name: str) -> Tag:
        attributes = {'ac:name': name, 'ac:schema-version': '1'}
        macro = bs4.BeautifulSoup().new_tag('ac:structured-macro', attrs=attributes)
        return macro

    def __is_template_soup_not_importing(self) -> bool:
        last_write = self._PAGE_TEMPLATE.find(class_='last_write').string
        return self.__is_date_longer_ago_than_yesterday(last_write)

    @staticmethod
    def __is_date_longer_ago_than_yesterday(date: str) -> bool:
        date_input = datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
        date_now = datetime.now()
        if date_now - date_input > timedelta(days=1):
            return True
        else:
            return False

    def __are_template_soup_imports_deviating(self) -> bool:
        if self.__DAILY_IMPORT_TRESHOLD is not None:
            threshold = int(self.__DAILY_IMPORT_TRESHOLD)
            border_lower = threshold * (1 - self.__WITDH_IMPORT_THRESHOLD)
            border_upper = threshold * (1 + self.__WITDH_IMPORT_THRESHOLD)
            imported = self._PAGE_TEMPLATE.find(class_='daily_imported').string
            updated = self._PAGE_TEMPLATE.find(class_='daily_updated').string
            if imported == '-' or updated == '-':
                return False
            sum_imports = int(imported) + int(updated)
            if border_lower <= sum_imports <= border_upper:
                return False
            else:
                return True
        return False

    def __is_template_soup_daily_error_rate_above_one(self) -> bool:
        error_rate = self._PAGE_TEMPLATE.find(class_='daily_error_rate').string
        if error_rate == '-':
            return False
        imported = self._PAGE_TEMPLATE.find(class_='daily_imported').string
        updated = self._PAGE_TEMPLATE.find(class_='daily_updated').string
        threshold = 1.0
        if not imported == '-' and not updated == '-':
            sum_imports = int(imported) + int(updated)
            if sum_imports <= 100:
                threshold = 5.0
        return float(error_rate) >= threshold


class TemplatePageJiraTableWriter(TemplatePageContentWriter):

    def __init__(self, id_node: str):
        mapper = ConfluenceNodeMapper()
        self.__LABELS_JIRA = mapper.get_node_value_from_mapping_dict(id_node, 'JIRA_LABELS')

    def _add_content_to_template_soup(self):
        if self.__LABELS_JIRA is not None and self.__LABELS_JIRA:
            query = self.__generate_jira_query_from_labels()
        else:
            query = 'project=AKTIN AND Labels=\"empty\"'
        table = self.__generate_jira_table_with_query(query)
        self._PAGE_TEMPLATE.find(class_='table_jira').replace_with(table)

    def __generate_jira_query_from_labels(self) -> str:
        tmp_labels = []
        for label in self.__LABELS_JIRA:
            tmp_labels.append(''.join(['Labels=\"', label, '\"']))
        query = ' OR '.join(tmp_labels)
        query = ' '.join(['project=AKTIN', 'AND', '(', query, ')'])
        return query

    def __generate_jira_table_with_query(self, query: str) -> Tag:
        param_server = self.__create_ac_parameter_tag('server', 'Jira IMI UK Aachen')
        param_id_columns = self.__create_ac_parameter_tag('columnIds', 'issuekey,summary,issuetype,created,updated,duedate,assignee,reporter,priority,status,resolution')
        param_columns = self.__create_ac_parameter_tag('columns', 'key,summary,type,created,updated,due,assignee,reporter,priority,status,resolution')
        param_max_issues = self.__create_ac_parameter_tag('maximumIssues', '25')
        param_query = self.__create_ac_parameter_tag('jqlQuery', query)
        frame = self.__create_ac_macro_tag('jira')
        frame.extend([param_server, param_id_columns, param_columns, param_max_issues, param_query])
        jira = bs4.BeautifulSoup().new_tag('p', attrs={'class': 'table_jira'})
        jira.append(frame)
        return jira

    @staticmethod
    def __create_ac_parameter_tag(name: str, content: str) -> Tag:
        parameter = bs4.BeautifulSoup().new_tag('ac:parameter', attrs={'ac:name': name})
        parameter.append(content)
        return parameter

    @staticmethod
    def __create_ac_macro_tag(name: str) -> Tag:
        attributes = {'ac:name': name, 'ac:schema-version': '1'}
        macro = bs4.BeautifulSoup().new_tag('ac:structured-macro', attrs=attributes)
        return macro


class TemplateResourceLoader(metaclass=SingletonMeta):

    def __init__(self):
        self.__DIR_TEMPLATES = os.environ['CONFLUENCE_RESOURCES_DIR']

    def get_resource_as_string(self, name_resource: str) -> str:
        path_resource = os.path.join(self.__DIR_TEMPLATES, name_resource)
        with open(path_resource, 'r') as resource:
            content = resource.read()
        return content

    def get_resource_as_soup(self, name_resource: str) -> bs4.BeautifulSoup:
        resource = self.get_resource_as_string(name_resource)
        return bs4.BeautifulSoup(resource, 'html.parser')


class TemplatePageMigrator(TemplatePageContentWriter):
    __FILENAME_TEMPLATE_PAGE: str = 'template_page.html'

    def __init__(self):
        self.__RESOURCE_LOADER = TemplateResourceLoader()

    def is_template_page_outdated(self, page_template: str) -> bool:
        template_new = self.__RESOURCE_LOADER.get_resource_as_soup(self.__FILENAME_TEMPLATE_PAGE)
        version_new = template_new.find(class_='version_template').string
        template_old = bs4.BeautifulSoup(page_template, 'html.parser')
        version_old = template_old.find(class_='version_template').string
        return version_new != version_old

    def _add_content_to_template_soup(self):
        template_new = self.__RESOURCE_LOADER.get_resource_as_soup(self.__FILENAME_TEMPLATE_PAGE)
        template_new = self.__migrate_clinic_information_to_new_template(template_new)
        template_new = self.__migrate_id_information_to_new_template(template_new)
        self._PAGE_TEMPLATE = template_new

    def __migrate_clinic_information_to_new_template(self, soup: bs4.BeautifulSoup) -> bs4.BeautifulSoup:
        soup = self.__migrate_key_to_new_template('clinic_name', soup)
        soup = self.__migrate_key_to_new_template('clinic_since', soup)
        soup = self.__migrate_key_to_new_template('information_system', soup)
        soup = self.__migrate_key_to_new_template('interface_import', soup)
        soup = self.__migrate_key_to_new_template('contact_ed', soup)
        soup = self.__migrate_key_to_new_template('contact_it', soup)
        return soup

    def __migrate_id_information_to_new_template(self, soup: bs4.BeautifulSoup) -> bs4.BeautifulSoup:
        soup = self.__migrate_key_to_new_template('root_patient', soup)
        soup = self.__migrate_key_to_new_template('format_patient', soup)
        soup = self.__migrate_key_to_new_template('root_encounter', soup)
        soup = self.__migrate_key_to_new_template('format_encounter', soup)
        soup = self.__migrate_key_to_new_template('root_billing', soup)
        soup = self.__migrate_key_to_new_template('format_billing', soup)
        return soup

    def __migrate_key_to_new_template(self, key: str, soup: bs4.BeautifulSoup) -> bs4.BeautifulSoup:
        value = self._PAGE_TEMPLATE.find(class_=key)
        soup.find(class_=key).replace_with(value)
        return soup


class ConfluencePageHandler:
    __FILENAME_TEMPLATE_PAGE: str = 'template_page.html'

    def __init__(self, id_node: str, dir_working=''):
        self.__CONFLUENCE = ConfluenceConnection()
        self.__CONFLUENCE_PARENT_PAGE = os.environ['CONFLUENCE_PARENT_PAGE']
        mapper = ConfluenceNodeMapper()
        self.__COMMON_NAME = mapper.get_node_value_from_mapping_dict(id_node, 'COMMON')
        self.__RESOURCE_LOADER = TemplateResourceLoader()
        self.__CSV_INFO_WRITER = TemplatePageCSVInfoWriter(id_node, dir_working)
        self.__CSV_ERROR_WRITER = TemplatePageCSVErrorWriter(id_node, dir_working)
        self.__NODE_RESOURCE_WRITER = TemplatePageNodeResourceWriter(id_node, dir_working)
        self.__STATUS_CHECKER = TemplatePageStatusChecker(id_node)
        self.__JIRA_TABLE_WRITER = TemplatePageJiraTableWriter(id_node)
        self.__TEMPLATE_MIGRATOR = TemplatePageMigrator()

    def upload_node_information_as_confluence_page(self):
        if not self.__CONFLUENCE.check_page_existence(self.__COMMON_NAME):
            page = self.__RESOURCE_LOADER.get_resource_as_string(self.__FILENAME_TEMPLATE_PAGE)
            self.__CONFLUENCE.create_confluence_page(self.__COMMON_NAME, self.__CONFLUENCE_PARENT_PAGE, page)
        else:
            page = self.__CONFLUENCE.get_page_content(self.__COMMON_NAME)
            if self.__TEMPLATE_MIGRATOR.is_template_page_outdated(page):
                page = self.__TEMPLATE_MIGRATOR.add_content_to_template_page(page)
        page = self.__write_content_to_page_template(page)
        self.__CONFLUENCE.update_confluence_page(self.__COMMON_NAME, page)

    def __write_content_to_page_template(self, template: str) -> str:
        template = self.__NODE_RESOURCE_WRITER.add_content_to_template_page(template)
        template = self.__CSV_INFO_WRITER.add_content_to_template_page(template)
        template = self.__CSV_ERROR_WRITER.add_content_to_template_page(template)
        template = self.__JIRA_TABLE_WRITER.add_content_to_template_page(template)
        template = self.__STATUS_CHECKER.add_content_to_template_page(template)
        return template


class CSVBackupManager:

    def __init__(self, id_node: str, dir_working=''):
        self.__DIR_WORKING = dir_working
        mapper = ConfluenceNodeMapper()
        self.__COMMON_NAME = mapper.get_node_value_from_mapping_dict(id_node, 'COMMON')
        self.__CONFLUENCE = ConfluenceConnection()

    def backup_csv_files(self):
        list_csv_files = self.__get_all_csv_files_in_directory()
        for name_csv in list_csv_files:
            path_csv = os.path.join(self.__DIR_WORKING, name_csv)
            self.__CONFLUENCE.upload_csv_as_attachement_to_page(self.__COMMON_NAME, path_csv)

    def __get_all_csv_files_in_directory(self) -> list:
        return [name_file for name_file in os.listdir(self.__DIR_WORKING) if name_file.endswith('.csv')]


class ConfluencePageHandlerManager:
    __CONFLUENCE_ROOT_PAGE_NAME = 'Support'

    def __init__(self):
        mapper = ConfluenceNodeMapper()
        self.__DICT_MAPPING = mapper.get_mapping_dict()
        self.__DIR_ROOT = os.environ['ROOT_DIR']
        self.__CONFLUENCE = ConfluenceConnection()
        self.__CONFLUENCE_PARENT_PAGE = os.environ['CONFLUENCE_PARENT_PAGE']
        self.__init_parent_page()

    def __init_parent_page(self):
        if not self.__CONFLUENCE.check_page_existence(self.__CONFLUENCE_PARENT_PAGE):
            macro = bs4.BeautifulSoup().new_tag('ac:structured-macro', attrs={'ac:name': 'children', 'ac:schema-version': '1'})
            page_parent = bs4.BeautifulSoup().new_tag('p')
            page_parent.append(macro)
            page_parent = str(page_parent)
            self.__CONFLUENCE.create_confluence_page(self.__CONFLUENCE_PARENT_PAGE, self.__CONFLUENCE_ROOT_PAGE_NAME, page_parent)

    def upload_csv_files_as_confluence_pages(self):
        for id_node in self.__DICT_MAPPING.keys():
            dir_working = os.path.join(self.__DIR_ROOT, id_node)
            if os.path.isdir(dir_working):
                handler = ConfluencePageHandler(id_node, dir_working)
                handler.upload_node_information_as_confluence_page()
                backup = CSVBackupManager(id_node, dir_working)
                backup.backup_csv_files()
            else:
                print('Directory for id %s not found. Skipping...' % id_node)


def main(path_config: str):
    try:
        __init_logger()
        load_properties_file_as_environment(path_config)
        manager = ConfluencePageHandlerManager()
        manager.upload_csv_files_as_confluence_pages()
    except Exception as e:
        logging.exception(e)
    finally:
        __stop_logger()


if __name__ == '__main__':
    if len(sys.argv) == 1:
        raise SystemExit('path to config file is missing')
    if len(sys.argv) > 2:
        raise SystemExit('invalid number of input arguments')
    main(sys.argv[1])
