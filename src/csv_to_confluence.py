# -*- coding: utf-8 -*
"""
Created on 22.03.2022
@AUTHOR=Alexander Kombeiz (akombeiz@ukaachen.de)
"""
#
#      Copyright (c) 2022  AKTIN
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

import bs4
import pandas as pd
from bs4.element import Tag
from packaging import version

from common import Main, CSVHandler, ConfluenceConnection, ConfluenceNodeMapper, ErrorCSVHandler, InfoCSVHandler, \
    ResourceLoader, SingletonABCMeta, SingletonMeta, TimestampHandler


class TemplatePageLoader(ResourceLoader):
    """
    Retrieves the confluence template page content as a string
    """
    __filename: str = 'template_page.html'
    __summary_filename: str = 'template_summmary.html'
    __encoding: str = 'utf-8'

    def get_template_page(self) -> str:
        return self._get_resource_as_string(self.__filename, self.__encoding)

    def get_template_summary(self) -> str:
        return self._get_resource_as_string(self.__summary_filename, self.__encoding)


class TemplatePageElementCreator(metaclass=SingletonMeta):
    """
    Creates commonly used html and confluence elements. Is also used to convert string
    template of confluence page to a searchable html soup
    """
    __parser: str = 'html.parser'

    def create_ac_parameter_element(self, name: str, content: str) -> Tag:
        parameter = bs4.BeautifulSoup(features=self.__parser).new_tag('ac:parameter', attrs={'ac:name': name})
        parameter.append(content)
        return parameter

    def create_ac_macro_element(self, name: str) -> Tag:
        attributes = {'ac:name': name, 'ac:schema-version': '1'}
        macro = bs4.BeautifulSoup(features=self.__parser).new_tag('ac:structured-macro', attrs=attributes)
        return macro

    def create_ac_link_element(self, pagename: str) -> bs4.BeautifulSoup:
        """
        bs4 seems not to be supporting self-closing HTML-Tags
        """
        link = f'<ac:link><ri:page ri:content-title="{pagename}" /></ac:link>'
        link = self.convert_element_to_soup(link)
        return link

    def create_th_html_element(self, name: str) -> Tag:
        header = bs4.BeautifulSoup(features=self.__parser).new_tag('th', attrs={'style': 'text-align: center;'})
        header.append(name)
        return header

    def create_td_html_element(self, content: str, centered=False) -> Tag:
        attributes = {'style': 'text-align: center;'} if centered else {}
        data = bs4.BeautifulSoup(features=self.__parser).new_tag('td', attrs=attributes)
        data.append(content)
        return data

    def create_html_element(self, elem_type: str, attributes=None) -> Tag:
        attributes = attributes or {}
        return bs4.BeautifulSoup(features=self.__parser).new_tag(elem_type, attrs=attributes)

    def convert_element_to_soup(self, elem) -> bs4.BeautifulSoup:
        return bs4.BeautifulSoup(str(elem), self.__parser)

    def get_parser(self) -> str:
        return self.__parser


class TemplatePageContentWriter(ABC, metaclass=SingletonABCMeta):
    """
    Base class for writing content to a Confluence page.
    """
    _encoding: str = 'utf-8'

    def __init__(self):
        self._creator = TemplatePageElementCreator()
        self._working_dir = os.getenv('DIR.WORKING')
        self._node_id = None
        self._node_working_dir = None
        self._page_template = None

    def add_content_to_template_page(self, template_page: str, node_id: str) -> str:
        self._node_id = node_id
        self._node_working_dir = os.path.join(self._working_dir, node_id)
        self._page_template = bs4.BeautifulSoup(template_page, self._creator.get_parser())
        self._add_content_to_template_soup()
        return str(self._page_template)

    @abstractmethod
    def _add_content_to_template_soup(self):
        """
        Abstract method to add content to the template page's BeautifulSoup object.
        """


class TemplatePageNodeResourceWriter(TemplatePageContentWriter):
    """
    Writes information about node resources from a text file to a Confluence page.

    The content of the 'versions' resource is more static compared to other resources. Each value is written into a
    predefined element. The other resources are concatenated and added to the page.
    """

    def _add_content_to_template_soup(self):
        self.__add_versions_to_template_soup()
        self.__add_rscript_to_template_soup()
        self.__add_python_to_template_soup()
        self.__add_import_scripts_to_template_soup()

    def __add_versions_to_template_soup(self):
        versions = self.__load_node_resource_as_dict('versions')
        self._page_template.find(class_='os').string.replace_with(self.__get_value_of_dict(versions, 'os'))
        self._page_template.find(class_='kernel').string.replace_with(self.__get_value_of_dict(versions, 'kernel'))
        self._page_template.find(class_='java').string.replace_with(self.__get_value_of_dict(versions, 'java'))
        self._page_template.find(class_='j2ee-impl').string.replace_with(
            self.__get_value_of_dict(versions, 'j2ee-impl'))
        self._page_template.find(class_='apache2').string.replace_with(self.__get_value_of_dict(versions, 'apache2'))
        self._page_template.find(class_='postgres').string.replace_with(self.__get_value_of_dict(versions, 'postgres'))
        self._page_template.find(class_='dwh-api').string.replace_with(self.__get_value_of_dict(versions, 'dwh-api'))
        self._page_template.find(class_='dwh-j2ee').string.replace_with(self.__get_value_of_dict(versions, 'dwh-j2ee'))

    def __add_rscript_to_template_soup(self):
        rscript_resource = self.__load_node_resource_as_dict('rscript')
        rscript = self.__concat_dict_items_as_string(rscript_resource)
        self._page_template.find(class_='rscript').string.replace_with(rscript)

    def __add_python_to_template_soup(self):
        python_resource = self.__load_node_resource_as_dict('python')
        python = self.__concat_dict_items_as_string(python_resource)
        self._page_template.find(class_='python').string.replace_with(python)

    def __add_import_scripts_to_template_soup(self):
        import_scripts_resource = self.__load_node_resource_as_dict('import-scripts')
        import_scripts = self.__concat_dict_items_as_string(import_scripts_resource)
        self._page_template.find(class_='import-scripts').string.replace_with(import_scripts)

    def __load_node_resource_as_dict(self, resource_name: str) -> dict:
        filename = ''.join([self._node_id, '_', resource_name, '.txt'])
        filepath = os.path.join(self._node_working_dir, filename)
        if not os.path.exists(filepath):
            return {}
        with open(filepath, encoding=self._encoding) as file:
            resource = json.load(file)
        return resource

    @staticmethod
    def __get_value_of_dict(dictionary: dict, key: str) -> str:
        if key not in dictionary:
            return '-'
        value = dictionary[key]
        if not value:
            return '-'
        return value

    @staticmethod
    def __concat_dict_items_as_string(dictionary: dict) -> str:
        tmp_list = []
        if not dictionary:
            return '-'
        for key, value in dictionary.items():
            value = '-' if not value else value
            item = ''.join([key, ' ', '(', value, ')'])
            tmp_list.append(item)
        return ', '.join(tmp_list)


class TemplatePageJiraTableWriter(TemplatePageContentWriter):
    """
    Creates a Jira query with values set in the mapping JSON (see ConfluenceNodeMapper) for a single broker node.
    Adds a table for Jira tickets as a custom Confluence HTML element.
    """

    def __init__(self):
        super().__init__()
        self.__mapper = ConfluenceNodeMapper()

    def _add_content_to_template_soup(self):
        """
        This method generates a Jira query based on the JIRA_LABELS value from the mapping JSON for the node.
        If the JIRA_LABELS value is not present or empty, a default query is used.
        The Jira table with the query is then added to the page.
        """
        jira_labels = self.__mapper.get_node_value_from_mapping_dict(self._node_id, 'JIRA_LABELS')
        if jira_labels is not None and jira_labels:
            query = self.__generate_jira_query_from_labels(jira_labels)
        else:
            query = 'project=AKTIN AND Labels="empty"'
        table = self.__generate_jira_table_with_query(query)
        self._page_template.find(class_='table_jira').replace_with(table)

    @staticmethod
    def __generate_jira_query_from_labels(labels_jira: str) -> str:
        tmp_labels = []
        for label in labels_jira:
            tmp_labels.append(''.join(['Labels="', label, '"']))
        query = ' OR '.join(tmp_labels)
        query = ' '.join(['project=AKTIN', 'AND', '(', query, ')'])
        return query

    def __generate_jira_table_with_query(self, query: str) -> Tag:
        server_param = self._creator.create_ac_parameter_element('server', 'Jira IMI Cloud')
        column_ids = self._creator.create_ac_parameter_element(
            'columnIds',
            'issuekey,summary,issuetype,created,updated,duedate,assignee,reporter,priority,status,resolution')
        column_param = self._creator.create_ac_parameter_element(
            'columns',
            'key,summary,type,created,updated,due,assignee,reporter,priority,status,resolution')
        max_issues_param = self._creator.create_ac_parameter_element('maximumIssues', '25')
        query_param = self._creator.create_ac_parameter_element('jqlQuery', query)
        frame = self._creator.create_ac_macro_element('jira')
        frame.extend([server_param, column_ids, column_param, max_issues_param, query_param])
        jira = self._creator.create_html_element('p', {'class': 'table_jira'})
        jira.append(frame)
        return jira


class ConfluenceClinicContactGrabber(TemplatePageContentWriter):
    """
    Searches another Confluence page for correspondents of a broker node ID.
    Correspondents are written as a table into the template.
    """
    __confluence_email_list: str = 'E-Mail-Verteiler'

    def __init__(self):
        super().__init__()
        self.__email_df = self.__grab_email_contacts_dataframe()

    def __grab_email_contacts_dataframe(self) -> pd.DataFrame:
        confluence = ConfluenceConnection()
        confluence_email_page = confluence.get_page_content(self.__confluence_email_list)
        email_table = pd.read_html(confluence_email_page)
        df = email_table[0]
        df.columns=df.iloc[0]
        df = df.iloc[1:].reset_index(drop=True)
        df['Node ID'] = pd.to_numeric(df['Node ID'])
        df = df.fillna('')
        return df

    def _add_content_to_template_soup(self):
        """
        This method generates tables for the 'IT' and 'Notaufnahme' contact types and replaces
        the corresponding placeholders in the template with these tables.
        """
        it_table = self.__generate_contact_table_for_contact_type('IT')
        self._page_template.find(class_='contact_it').replace_with(it_table)
        ed_table = self.__generate_contact_table_for_contact_type('Notaufnahme')
        self._page_template.find(class_='contact_ed').replace_with(ed_table)

    def __generate_contact_table_for_contact_type(self, contact_type: str) -> Tag:
        contacts = self.__get_contacts_for_contact_type(contact_type)
        contact_rows = []
        for name, email in contacts.items():
            contact_row = self.__generate_contact_row(name, email)
            contact_rows.append(contact_row)
        table = self.__generate_contact_table_frame(contact_type)
        table.find('tbody').extend(contact_rows)
        return table

    def __get_contacts_for_contact_type(self, contact_type: str) -> dict:
        """
        contact_type must be either 'IT' or 'Notaufnahme'
        """
        list_idx = self.__email_df.index[self.__email_df['Node ID'] == int(self._node_id)].tolist()
        df_node = self.__email_df.iloc[list_idx]
        df_contacts = df_node[df_node['Ansprechpartner für'] == contact_type]
        contacts = {}
        for row in df_contacts.iterrows():
            row = row[1]
            name = ' '.join([row['Titel'], row['Vorname'], row['Nachname']])
            name = name.strip()
            contacts[name] = row['Kontakt']
        return contacts

    def __generate_contact_row(self, name: str, email: str) -> Tag:
        td_name = self._creator.create_td_html_element(name, centered=True)
        mail_link = self._creator.create_html_element('a', {'href': ':'.join(['mailto', email])})
        mail_link.append(email)
        td_mail = self._creator.create_td_html_element(mail_link)
        tr = self._creator.create_html_element('tr')
        tr.append(td_name)
        tr.append(td_mail)
        return tr

    def __generate_contact_table_frame(self, contact_type: str) -> bs4.BeautifulSoup:
        if contact_type == 'IT':
            classname = 'contact_it'
        elif contact_type == 'Notaufnahme':
            classname = 'contact_ed'
        else:
            raise SystemExit('invalid contact type')
        tbody = self._creator.create_html_element('tbody')
        table = self._creator.create_html_element('table', {'class': 'wrapped'})
        table.append(tbody)
        td = self._creator.create_html_element('td', {'class': classname})
        td.append(table)
        return td


class TemplatePageClinicInfoWriter(TemplatePageContentWriter):
    """
    Writes (mostly) static information about the clinic to a Confluence page.
    """

    def __init__(self):
        super().__init__()
        self.__mapper = ConfluenceNodeMapper()

    def _add_content_to_template_soup(self):
        """
        This method retrieves information from the mapping dictionary using specific keys and
        replaces corresponding placeholders in the template with the retrieved values.
        """
        self.__add_value_from_mapping_to_page_template('LONG_NAME', 'clinic_name')
        self.__add_value_from_mapping_to_page_template('HOSPITAL_INFORMATION_SYSTEM', 'information_system')
        self.__add_value_from_mapping_to_page_template('IMPORT_INTERFACE', 'interface_import')
        self.__add_clinic_ids('ROOT')
        self.__add_clinic_ids('FORMAT')

    def __add_value_from_mapping_to_page_template(self, mapping_key: str, page_key: str):
        value = self.__mapper.get_node_value_from_mapping_dict(self._node_id, mapping_key)
        if not value or value is None:
            value = 'changeme'
        self._page_template.find(class_=page_key).string.replace_with(value)

    def __add_clinic_ids(self, type_ids: str):
        ids_dict = self.__mapper.get_node_value_from_mapping_dict(self._node_id, type_ids)
        for key in ['PATIENT', 'ENCOUNTER', 'BILLING']:
            value = 'changeme'
            if ids_dict is not None and key in ids_dict:
                value = ids_dict[key]
            self._page_template.find(class_='_'.join([type_ids.lower(), key.lower()])).string.replace_with(value)


class TemplatePageCSVContentWriter(TemplatePageContentWriter, ABC):
    """
    Used to write content from csv file to confluence page
    """
    _handler: CSVHandler

    def __init__(self):
        super().__init__()
        self._timestamp_handler = TimestampHandler()
        self._df = None

    def add_content_to_template_page(self, template_page: str, node_id: str) -> str:
        self._node_id = node_id
        self._page_template = bs4.BeautifulSoup(template_page, self._creator.get_parser())
        dir_working = os.path.join(self._working_dir, node_id)
        self._df = self.__load_csv_as_df(node_id, dir_working)
        self._add_content_to_template_soup()
        return str(self._page_template)

    def __load_csv_as_df(self, node_id: str, working_dir: str) -> pd.DataFrame:
        name_csv = self._handler.generate_node_csv_name(node_id)
        path_csv = os.path.join(working_dir, name_csv)
        return self._handler.read_csv_as_df(path_csv)


# TODO bei last-import soll der tatsächliche last import stehen
class TemplatePageCSVInfoWriter(TemplatePageCSVContentWriter):
    """
    Writes the content of an info CSV (of a single node) into predefined elements of the template.
    """

    def __init__(self):
        super().__init__()
        self._handler = InfoCSVHandler()

    def _add_content_to_template_soup(self):
        self.__add_dates_to_template_soup()
        self.__add_weekly_imports_to_template_soup()
        self.__add_daily_imports_to_template_soup()

    def __add_dates_to_template_soup(self):
        fields = {
            'date': 'last_check',
            'last_contact': 'last_contact',
            'last_start': 'last_start',
            'last_write': 'last_write',
            'last_reject': 'last_reject',
        }
        last_row = self._df.iloc[-1].to_dict()
        for field, template_class in fields.items():
            time = last_row.get(field)
            if time is not None and time != '-':
                time = self._timestamp_handler.convert_ts_to_berlin_time(time)
                time = time[:19]
            else:
                time = '-'
            self._page_template.find(class_=template_class).string.replace_with(time)

    def __add_weekly_imports_to_template_soup(self):
        fields = {
            'daily_imported': 'imported',
            'daily_updated': 'updated',
            'daily_invalid': 'invalid',
            'daily_failed': 'failed',
            'daily_error_rate': 'error_rate',
        }
        last_week = self._df.tail(7)
        for field, template_class in fields.items():
            mean = self.__get_mean_of_series(last_week[field])
            self._page_template.find(class_=template_class).string.replace_with(mean)

    @staticmethod
    def __get_mean_of_series(series: pd.Series) -> str:
        length = len(series)
        series = series[series != '-']  # drop the rows
        if series.empty:
            return '-'
        mean = series.astype(float).sum() / length
        return f'{mean:.2f}'

    def __add_daily_imports_to_template_soup(self):
        last_row = self._df.iloc[-1].to_dict()
        fields = ['daily_imported', 'daily_updated', 'daily_invalid', 'daily_failed', 'daily_error_rate']
        for field in fields:
            self._page_template.find(class_=field).string.replace_with(last_row.get(field))


class TemplatePageCSVErrorWriter(TemplatePageCSVContentWriter):
    """
    Writes content of error CSV (of a single node) into predefined elements of the template.
    """
    __num_errors: int = 20

    def __init__(self):
        super().__init__()
        self._handler = ErrorCSVHandler()

    def _add_content_to_template_soup(self):
        """
        Adds error content to the template soup by creating a confluence error table.
        """
        error_table = self.__create_confluence_error_table()
        self._page_template.find(class_='table_errors_body').replace_with(error_table)

    def __create_confluence_error_table(self) -> Tag:
        errors_list = self._df.head(self.__num_errors).to_dict('records')
        errors_rows = []
        for error in errors_list:
            row = self.__create_error_table_row(error['timestamp'], error['repeats'], error['content'])
            errors_rows.append(row)
        table = self.__generate_empty_error_table()
        table.find('tbody').extend(errors_rows)
        return table

    def __create_error_table_row(self, timestamp: str, repeats: str, content: str) -> Tag:
        timestamp = self._timestamp_handler.get_utc_ymd_hms_from_date_string(timestamp)
        timestamp_column = self._creator.create_td_html_element(timestamp, centered=True)
        repeats_column = self._creator.create_td_html_element(repeats, centered=True)
        content_column = self._creator.create_td_html_element(content)
        row = self._creator.create_html_element('tr')
        row.extend([timestamp_column, repeats_column, content_column])
        return row

    def __generate_empty_error_table(self) -> bs4.BeautifulSoup:
        header = self.__create_error_table_header()
        table = self._creator.create_html_element('tbody', {'class': 'table_errors_body'})
        table.append(header)
        table = self._creator.convert_element_to_soup(table)
        return table

    def __create_error_table_header(self) -> Tag:
        timestamp_header = self._creator.create_th_html_element('timestamp')
        repeats_header = self._creator.create_th_html_element('repeats')
        content_header = self._creator.create_th_html_element('content')
        header = self._creator.create_html_element('tr')
        header.extend([timestamp_header, repeats_header, content_header])
        return header


class TemplatePageStatusChecker(TemplatePageCSVContentWriter):
    """
    Checks import and connection status inside (template of) confluence page and sets
    status as a custom HTML element.
    Should always be the last class called in the processing pipeline!
    """
    __default_threshold_hours_failure = 72
    __default_days_of_consecutive_imports = 3

    def __init__(self):
        super().__init__()
        self._handler = InfoCSVHandler()
        self._mapper = ConfluenceNodeMapper()

    def _add_content_to_template_soup(self):
        self.__append_last_year_rows_to_df_if_necessary()
        if self.__has_csv_a_gap_in_broker_connection():
            status = self.__create_status_element('GAP IN MONITORING', 'Red')
        elif self.__is_template_soup_still_testing():
            status = self.__create_status_element('TESTING', 'Blue')
        elif self.__is_template_soup_offline():
            status = self.__create_status_element('OFFLINE', 'Red')
        elif self.__is_template_soup_not_importing():
            status = self.__create_status_element('NO IMPORTS', 'Red')
        elif self.__is_template_soup_daily_error_rate_above_threshold(10.0):
            status = self.__create_status_element('EXTREME ERROR RATE', 'Red')
        elif self.__is_template_soup_daily_error_rate_above_threshold(5.0):
            status = self.__create_status_element('HIGH ERROR RATE', 'Yellow')
        elif self.__is_template_soup_daily_error_rate_above_threshold(1.0):
            status = self.__create_status_element('LOW ERROR RATE', 'Yellow')
        else:
            status = self.__create_status_element('ONLINE', 'Green')
        self._page_template.find(class_='status').replace_with(status)

    # TODO test missing
    def __append_last_year_rows_to_df_if_necessary(self):
        """
        If the CSV has less than set rows, try to append the previous year's CSV
        to this CSV.
        """
        if len(self._df) < self.__default_days_of_consecutive_imports:
            current_year = self._timestamp_handler.get_current_year()
            last_year = str(int(current_year) - 1)
            last_years_csv_name = self._handler.generate_node_csv_name(self._node_id, last_year)
            last_years_csv_path = os.path.join(self._working_dir, self._node_id, last_years_csv_name)
            if os.path.isfile(last_years_csv_path):
                last_years_df = self._handler.read_csv_as_df(last_years_csv_path)
                self._df = pd.concat([last_years_df, self._df], ignore_index=True)

    def __has_csv_a_gap_in_broker_connection(self) -> bool:
        """
        Checks if the CSV has a gap in the broker connection by comparing the timestamps.
        """
        series = self._df['date']
        if series.empty:
            return False
        todays_csv = series.iloc[-1]
        current_date = self._timestamp_handler.get_current_date()
        delta = self._timestamp_handler.get_timedelta_in_absolute_hours(current_date, todays_csv)
        if delta > 24:
            return True
        if len(series) >= 2:
            yesterdays_csv = series.iloc[-2]
            delta2 = self._timestamp_handler.get_timedelta_in_absolute_hours(yesterdays_csv, todays_csv)
            if delta2 > 24:
                return True
        return False

    def __is_template_soup_still_testing(self) -> bool:
        """
        Checks if the node is still testing by verifying the consecutive days of imports.
        If the set value for consecutive days is higher than the number of rows in the csv file,
        the check is dropped and False is returned.
        """
        consecutive_imports = self._mapper.get_node_value_from_mapping_dict(self._node_id, 'CONSECUTIVE_IMPORT_DAYS')
        if not consecutive_imports or consecutive_imports is None:
            consecutive_imports = self.__default_days_of_consecutive_imports
        series = self._df['daily_imported']
        if len(series) < consecutive_imports:
            return False
        series = series.str.replace('-', '0')
        series = pd.to_numeric(series)
        count = 0
        for value in series:
            if value > 0:
                count += 1
                if count == consecutive_imports:
                    return False
            else:
                count = 0
        return True

    def __is_template_soup_offline(self) -> bool:
        last_contact = self._df['last_contact'].iloc[-1]
        return self.__is_date_longer_ago_than_set_hours(last_contact)

    def __is_template_soup_not_importing(self) -> bool:
        last_write = self._df['last_write'].iloc[-1]
        if last_write == '-':
            series = self._df['last_write']
            filtered_series = series[series != '-']
            if filtered_series.empty:
                return False
            last_write = filtered_series.iloc[-1]
        return self.__is_date_longer_ago_than_set_hours(last_write)

    def __is_date_longer_ago_than_set_hours(self, input_date: str) -> bool:
        """
        Checks if the date is longer ago than the set threshold hours.
        """
        threshold_hours = self._mapper.get_node_value_from_mapping_dict(self._node_id, 'THRESHOLD_HOURS_FAILURE')
        if not threshold_hours or threshold_hours is None:
            threshold_hours = self.__default_threshold_hours_failure
        current_date = self._timestamp_handler.get_current_date()
        delta = self._timestamp_handler.get_timedelta_in_absolute_hours(input_date, current_date)
        return delta > threshold_hours

    def __is_template_soup_daily_error_rate_above_threshold(self, threshold: float) -> bool:
        error_rate = self._df['daily_error_rate'].iloc[-1]
        if error_rate == '-':
            return False
        return float(error_rate) >= threshold

    def __create_status_element(self, title: str, color: str) -> Tag:
        title_param = self._creator.create_ac_parameter_element('title', title)
        color_param = self._creator.create_ac_parameter_element('color', color)
        frame = self._creator.create_ac_macro_element('status')
        frame.extend([title_param, color_param])
        status = self._creator.create_html_element('td', {'style': 'text-align:center;', 'class': 'status'})
        status.append(frame)
        return status


class TemplatePageMonitoringStartDateWriter(TemplatePageCSVContentWriter):
    """
    Just adds monitoring start date for corresponding node to the Confluence page.
    """

    def __init__(self):
        super().__init__()
        self._handler = InfoCSVHandler()

    def _add_content_to_template_soup(self):
        first_monitoring = self._df['date'].iloc[0]
        start_monitoring = self._timestamp_handler.convert_ts_to_berlin_time(first_monitoring)
        start_monitoring = start_monitoring[:10]  # cutoff HH:MM:SS
        time_element = self._creator.create_html_element('time', {'datetime': start_monitoring})
        td = self._creator.create_html_element('td', {'class': 'online_since'})
        td.append(time_element)
        self._page_template.find(class_='online_since').replace_with(td)


class TemplatePageMigrator:
    """
    Migrates information that is only set once in the Confluence page (like monitoring start date)
    to a newer version of the corresponding template.
    """

    def __init__(self):
        self.__loader = TemplatePageLoader()
        self.__creator = TemplatePageElementCreator()

    def is_template_page_outdated(self, template_page: str) -> bool:
        """
        Checks if the provided page_template is outdated compared to the current template.
        """
        current_template = self.__loader.get_template_page()
        new_template = self.__creator.convert_element_to_soup(current_template)
        new_version = new_template.find(class_='version_template').string
        old_template = bs4.BeautifulSoup(template_page, 'html.parser')
        old_version = old_template.find(class_='version_template').string
        return version.parse(new_version) > version.parse(old_version)

    def migrate_page_template_to_newer_version(self, template_page: str) -> str:
        current_template = self.__loader.get_template_page()
        new_template = self.__creator.convert_element_to_soup(current_template)
        old_template = bs4.BeautifulSoup(template_page, 'html.parser')
        new_template = self.__migrate_key_from_old_to_new_template('online_since', old_template, new_template)
        return str(new_template)

    @staticmethod
    def __migrate_key_from_old_to_new_template(key: str, old_soup: bs4.BeautifulSoup, new_soup: bs4.BeautifulSoup) -> bs4.BeautifulSoup:
        value = old_soup.find(class_=key)
        new_soup.find(class_=key).replace_with(value)
        return new_soup


class ConfluenceHandler(ABC, metaclass=SingletonABCMeta):
    _confluence_root_page: str = 'Support'
    _confluence_parent_page: str = 'Support Log Broker-Monitor'

    def __init__(self):
        self._mapper = ConfluenceNodeMapper()
        self._confluence = ConfluenceConnection()


class ConfluencePageHandler(ConfluenceHandler):
    """
    Creates a new Confluence page for a single broker node. The name of a Confluence
    page is its common name (from Confluence node mapping JSON).
    """

    def __init__(self):
        super().__init__()
        self.__loader = TemplatePageLoader()
        self.__start_date_writer = TemplatePageMonitoringStartDateWriter()
        self.__migrator = TemplatePageMigrator()
        self.__content_writers = [
            TemplatePageClinicInfoWriter(),
            ConfluenceClinicContactGrabber(),
            TemplatePageCSVInfoWriter(),
            TemplatePageCSVErrorWriter(),
            TemplatePageNodeResourceWriter(),
            TemplatePageJiraTableWriter(),
            TemplatePageStatusChecker()
        ]

    def upload_node_information_as_confluence_page(self, node_id: str):
        common_name = self._mapper.get_node_value_from_mapping_dict(node_id, 'COMMON_NAME')
        if not self._confluence.does_page_exists(common_name):
            page = self.__loader.get_template_page()
            page = self.__start_date_writer.add_content_to_template_page(page, node_id)
            self._confluence.create_confluence_page(common_name, self._confluence_parent_page, page)
        page = self._confluence.get_page_content(common_name)
        if self.__migrator.is_template_page_outdated(page):
            page = self.__migrator.migrate_page_template_to_newer_version(page)
        page = self.__write_content_to_page_template(page, node_id)
        self._confluence.update_confluence_page(common_name, page)

    def __write_content_to_page_template(self, template: str, node_id: str) -> str:
        for content_writer in self.__content_writers:
            template = content_writer.add_content_to_template_page(template, node_id)
        return template


class SummaryTableCreator:
    """
    Creates summary tables for displaying information in HTML format.
    """

    def __init__(self):
        self.__creator = TemplatePageElementCreator()

    def create_summary_table_frame(self) -> bs4.BeautifulSoup:
        colgroup = self.__creator.create_html_element('colgroup')
        col = self.__creator.create_html_element('col')
        colgroup.append(col)
        table = self.__creator.create_html_element('table')
        table.append(colgroup)
        return table

    def create_empty_summary_table(self) -> bs4.BeautifulSoup:
        header = self.__create_summary_table_header()
        summary_table = self.__creator.create_html_element('tbody', {'class': 'table_summary_body'})
        summary_table.append(header)
        summary_table = self.__creator.convert_element_to_soup(summary_table)
        return summary_table

    def __create_summary_table_header(self) -> Tag:
        node = self.__creator.create_th_html_element('Node')
        interface = self.__creator.create_th_html_element('Interface')
        status = self.__creator.create_th_html_element('Status')
        last_check = self.__creator.create_th_html_element('Letzter Check')
        todays_error_rate = self.__creator.create_th_html_element('Fehlerrate heute')
        last_weeks_error_rate = self.__creator.create_th_html_element('Fehlerrate über 7 Tage')
        todays_imports = self.__creator.create_th_html_element('Imports heute')
        todays_errors = self.__creator.create_th_html_element('Fehler heute')
        header = self.__creator.create_html_element('tr')
        header.extend([node, interface, last_check, status, todays_imports, todays_errors, todays_error_rate, last_weeks_error_rate])
        return header

    def create_summary_table_row_from_confluence_page(self, commonname: str, confluence_page: str) -> Tag:
        template = self.__creator.convert_element_to_soup(confluence_page)
        node_link = self.__creator.create_ac_link_element(commonname)
        node = self.__creator.create_html_element('td', {'style': 'text-align: left;'})
        node.append(node_link)
        status_element = template.find(class_='status')
        interface = self.__create_table_data_from_page_template_key(template, 'interface_import')
        status = self.__creator.create_td_html_element(status_element.contents[0], centered=True)
        last_check = self.__create_table_data_from_page_template_key(template, 'last_check')
        todays_error_rate = self.__create_table_data_from_page_template_key(template, 'daily_error_rate')
        last_weeks_error_rate = self.__create_table_data_from_page_template_key(template, 'error_rate')
        todays_imports = self.__get_sum_of_two_table_data_elements(template, 'daily_imported', 'daily_updated')
        todays_errors = self.__get_sum_of_two_table_data_elements(template, 'daily_invalid', 'daily_failed')
        row = self.__creator.create_html_element('tr')
        row.extend([node, interface, last_check, status, todays_imports, todays_errors, todays_error_rate, last_weeks_error_rate])
        return row

    def __create_table_data_from_page_template_key(self, template_page: bs4.BeautifulSoup, key: str) -> Tag:
        value = template_page.find(class_=key).string
        td = self.__creator.create_td_html_element(value, centered=True)
        return td

    def __get_sum_of_two_table_data_elements(self, template_page: bs4.BeautifulSoup, key1: str, key2: str) -> Tag:
        value1 = template_page.find(class_=key1).string
        value2 = template_page.find(class_=key2).string
        if value1 == '-' and value2 == '-':
            sum_values = '-'
        else:
            value1 = float(value1) if value1 != '-' else 0.0
            value2 = float(value2) if value2 != '-' else 0.0
            sum_values = round(value1 + value2, 2)
        td = self.__creator.create_td_html_element(str(sum_values), centered=True)
        return td

class ConfluencePageHandlerManager(ConfluenceHandler):
    """
    Manages ConfluencePageHandlers for each broker node and performs various operations.
    """

    def __init__(self):
        super().__init__()
        self.__working_dir = os.getenv('DIR.WORKING')
        self.__resources_dir = os.getenv('DIR.RESOURCES')
        self.__space = os.getenv('CONFLUENCE.SPACE')
        self.__handler = ConfluencePageHandler()
        self.__summary = SummaryTableCreator()
        self.__csv_handler = InfoCSVHandler()
        self.__creator = TemplatePageElementCreator()
        self.__init_parent_page()

    def __init_parent_page(self):
        if not self._confluence.does_page_exists(self._confluence_parent_page):
            self._confluence.create_confluence_page(self._confluence_parent_page, self._confluence_root_page, "")

    def upload_node_information_as_confluence_pages(self):
        node_ids = self._mapper.get_all_keys()
        for node_id in node_ids:
            node_dir = os.path.join(self.__working_dir, node_id)
            if os.path.isdir(node_dir):
                self.__handler.upload_node_information_as_confluence_page(node_id)
            else:
                logging.info('Directory for id %s not found. Skipping...', node_id)

    def upload_summary_for_confluence_pages(self):
        node_ids = self._mapper.get_all_keys()
        tbody = self.__summary.create_empty_summary_table()
        for node_id in node_ids:
            common_name = self._mapper.get_node_value_from_mapping_dict(node_id, 'COMMON_NAME')
            if self._confluence.does_page_exists(common_name):
                page = self._confluence.get_page_content(common_name)
                row = self.__summary.create_summary_table_row_from_confluence_page(common_name, page)
                tbody.find('tbody').append(row)
        table = self.__summary.create_summary_table_frame()
        table.append(tbody)
        self._confluence.update_confluence_page(self._confluence_parent_page, str(table))


if __name__ == '__main__':
    if len(sys.argv) == 1:
        raise SystemExit(f'Usage: python {__file__} <path_to_config.toml>')
    Main.main(sys.argv[1], lambda: ConfluencePageHandlerManager().upload_node_information_as_confluence_pages())
    Main.main(sys.argv[1], lambda: ConfluencePageHandlerManager().upload_summary_for_confluence_pages())
