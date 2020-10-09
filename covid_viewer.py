from bokeh.layouts import row, column                        # type: ignore
from bokeh.models import ColumnDataSource, CustomJS, Select  # type: ignore
from bokeh.plotting import figure                            # type: ignore
from bokeh.io import output_file, show                       # type: ignore
from datetime import datetime
from matplotlib.dates import DateFormatter                   # type: ignore
from sys import argv, exit
import matplotlib.pyplot as plt                              # type: ignore
import pandas as pd                                          # type: ignore
import requests

usage_msg = ("""Usage: covid_viewer <country> <total/daily> [--update] [--help]
    --update\t\tupdate the local COVID data copy from JHU
    --help\t\tdisplay this help message

Copyright (c) 2020 by Corinna Buerger""")

JHU_RESPONSE_MIN_LENGTH = 100000
JHU_UPDATED_DATA_FILENAME = "covid_deaths.csv"  # NOTE: potentially overrides


class CovidData():
    def __init__(self, infile="covid_deaths.csv"):
        # pd.DataFrame for total death cases
        self.df_total = pd.read_csv(infile)

        self.start = self.df_total.columns[4]
        self.today = self.df_total.columns[-1]
        self.dates = pd.date_range(self.start, self.today).date

        # no country selected yet
        self.selected = None
        self.world_data = None

        # will be filled and transformed into self.df_daily
        self.daily_deaths = {}

        # DataFrame for daily death cases
        self.df_daily = self.get_daily_deaths()

        # adds worldwide death cases to both DataFrames
        self.get_world_deaths()

    def get_world_deaths(self):
        # append to DataFrame for total deaths
        world_total = {}
        for column_in_df in self.df_total.columns:
            world_total[column_in_df] = None

        for col_idx in range(0, len(self.df_total.columns)):
            column = self.df_total.columns[col_idx]
            if col_idx < 4:
                # here is no data for death cases
                world_total[column] = "World"
            else:
                for row_idx in range(0, len(self.df_total)):
                    if row_idx == 0:
                        # for the first row (country) in each column (day)
                        # the death cases will be assigned
                        world_total[column] = self.df_total.iloc[row_idx,
                                                                 col_idx]
                    else:
                        # for all the other rows (countries) in each column
                        # (day) the death cases will be added to the previous
                        # one
                        world_total[column] += self.df_total.iloc[row_idx,
                                                                  col_idx]

        self.df_total = self.df_total.append(world_total, ignore_index=True)

        # append to DataFrame for daily deaths (works just like for total
        # deaths but uses self.df_daily)
        world_daily = {}
        for column in self.df_daily.columns:
            world_daily[column] = None

        for col_idx in range(0, len(self.df_daily.columns)):
            column = self.df_daily.columns[col_idx]
            if col_idx < 4:
                world_daily[column] = "World"
            else:
                for row_idx in range(0, len(self.df_daily)):
                    if row_idx == 0:
                        world_daily[column] = self.df_daily.iloc[row_idx,
                                                                 col_idx]
                    else:
                        world_daily[column] += self.df_daily.iloc[row_idx,
                                                                  col_idx]

        self.df_daily = self.df_daily.append(world_daily, ignore_index=True)

    def get_daily_deaths(self):
        for column_in_df in self.df_total.columns:
            self.daily_deaths[column_in_df] = []

        for row_idx in range(0, len(self.df_total)):
            for col_idx in range(0, len(self.df_total.columns)):
                column = self.df_total.columns[col_idx]
                if col_idx <= 4:
                    # concerns all columns that do not contain data of death
                    # cases as well as for the first day of documentation
                    self.daily_deaths[column].append(self.df_total.
                                                     iloc[row_idx, col_idx])
                else:
                    # calculates the difference between today and yesterday
                    self.daily_deaths[column].append(
                            self.df_total.iloc[row_idx, col_idx] -
                            self.df_total.iloc[row_idx, col_idx-1])

        # created dict can now be transformed into a DataFrame
        return pd.DataFrame(self.daily_deaths)

    def select_country(self, name="US"):
        s_daily = self.df_daily[self.df_daily["Country/Region"]
                                == name].iloc[:, 4:]
        s_total = self.df_total[self.df_total["Country/Region"]
                                == name].iloc[:, 4:]
        self.world_data_daily = self.df_daily[self.df_daily["Country/Region"]
                                              == "World"].iloc[:, 4:]
        self.world_data_total = self.df_total[self.df_total["Country/Region"]
                                              == "World"].iloc[:, 4:]

        s_daily = s_daily.transpose()
        s_total = s_total.transpose()
        self.world_data_daily = self.world_data_daily.transpose()
        self.world_data_total = self.world_data_total.transpose()

        # only doing this for daily data can maybe lead to bugs
        col_names = s_daily.columns.tolist()
        if (len(col_names) > 1):
            print("changing just the first column's name to {}".format(name))
        s_daily = s_daily.rename(columns={col_names[0]: name})
        self.selected = s_daily

    def plot_selected_country(self, name, module="bokeh"):
        if self.selected is None:
            raise ValueError("no country selected")

        # create dictionary out of df that can be put into JS function
        grouped_df_d = self.df_daily.groupby("Country/Region", sort=False)
        grouped_df_t = self.df_total.groupby("Country/Region", sort=False)
        grouped_list_d = grouped_df_d.apply(lambda x: x.to_dict(orient="list"))
        grouped_list_t = grouped_df_t.apply(lambda x: x.to_dict(orient="list"))
        df_dict_nested_d = grouped_list_d.to_dict()
        df_dict_nested_t = grouped_list_t.to_dict()
        df_dict_daily = {}
        df_dict_total = {}
        keys_to_ignore = ["Province/State", "Country/Region", "Lat", "Long"]
        for key, value in df_dict_nested_d.items():
            helper_list = []
            for key_two, value_two in value.items():
                if key_two in keys_to_ignore:
                    continue
                else:
                    # sums up countries that occur multiple times
                    helper_list.append(sum(value_two))
            df_dict_daily[key] = helper_list
        for key, value in df_dict_nested_t.items():
            helper_list = []
            for key_two, value_two in value.items():
                if key_two in keys_to_ignore:
                    continue
                else:
                    # sums up countries that occur multiple times
                    helper_list.append(sum(value_two))
            df_dict_total[key] = helper_list

        dates = []
        for date_str in self.selected.index:
            date_obj = datetime.strptime(date_str, '%m/%d/%y')
            dates.append(date_obj)
        df_dict_daily["dates"] = dates
        df_dict_total["dates"] = dates


        if module == "bokeh":

            # also necessary to make it compatible with JS function
            df_dict_daily["selected"] = df_dict_daily[name]
            df_dict_total["selected"] = df_dict_total[name]
            source_daily = ColumnDataSource(data=df_dict_daily)
            source_total = ColumnDataSource(data=df_dict_total)

            # create two plots
            xaxis_label = "Date"
            yaxis_label = "Death Cases"
            legend_loc = "top_left"

            colors = ["lightgray", "blue"]
            pd = figure(x_axis_type="datetime")
            pt = figure(x_axis_type="datetime")

            pd.vbar(x='dates', color=colors[0], top="World",
                    source=source_daily,
                    width=0.9, legend_label="Worldwide")
            pd.vbar(x='dates', color=colors[1], top="selected",
                    source=source_daily, width=0.9,
                    legend_label="Selected Country")
            pd.legend.location = legend_loc
            pd.yaxis.axis_label = yaxis_label
            pd.xaxis.axis_label = xaxis_label

            pt.vbar(x='dates', color=colors[0], top="World",
                    source=source_total,
                    width=0.9, legend_label="Worldwide")
            pt.vbar(x='dates', color=colors[1], top="selected",
                    source=source_total, width=0.9,
                    legend_label="Selected Country")
            pt.legend.location = legend_loc
            pt.yaxis.axis_label = yaxis_label
            pt.xaxis.axis_label = xaxis_label

            output_file("test.html")

            # dropdown menu
            options = [*df_dict_daily.keys()]
            select = Select(title="Select a country", value=name,
                            options=options)
            with open("main.js", "r") as f:
                select.js_on_change("value", CustomJS(
                    args=dict(source_d=source_daily, source_t=source_total,
                              df_dict_t=df_dict_total, df_dict_d=df_dict_daily,
                              which_function="update-ctry"), code=f.read()))

            plots = row(pd, pt)
            show(column(select, plots))

        if module == "mpl":

            death_cases = []
            death_cases_world = []
            # cave: only for daily
            for sub_arr in self.selected.values:
                death_cases.append(sub_arr[0])
            for sub_arr in self.world_data_daily.values:
                death_cases_world.append(sub_arr[0])

            fig, ax = plt.subplots()
            date_format = DateFormatter("%d %b %Y")
            world_plot = ax.bar(dates, death_cases_world,
                                bottom=0, color="lightgray")
            country_plot = ax.bar(dates, death_cases, bottom=0)
            ax.set(xlabel="Date", ylabel="Death Cases")
            ax.xaxis.set_major_formatter(date_format)
            fig.subplots_adjust(bottom=0.175)
            plt.xticks(rotation=35, fontsize=7)
            plt.legend((world_plot[0], country_plot[0]),
                       ("Worldwide", "{}".format(name)))
            plt.show()

    @staticmethod
    def update_local_data():
        base_url = "https://raw.githubusercontent.com/"
        url = (base_url +
               "CSSEGISandData/COVID-19/" +
               "master/csse_covid_19_data/" +
               "csse_covid_19_time_series/" +
               "time_series_covid19_deaths_global.csv")

        response = requests.get(url)

        if response.status_code == 200:
            content = response.content
            if len(content) < JHU_RESPONSE_MIN_LENGTH:
                print("got a very short response, aborting")
                exit(1)
            csv_file = open(JHU_UPDATED_DATA_FILENAME, "wb")
            csv_file.write(content)
            csv_file.close()
            print("successfully updated {}".
                  format(JHU_UPDATED_DATA_FILENAME))

    @staticmethod
    def usage():
        print(usage_msg)


if __name__ == "__main__":
    if len(argv) < 2:
        CovidData.usage()
        exit(1)

    for param in argv:
        if param == "--update":
            CovidData.update_local_data()
        if param == "--help":
            CovidData.usage()

    # TODO: validate, that country exists in df,
    #       otherwise use a sensible default
    if argv[1].lower() == "us" or argv[1].lower() == "usa":
        country = "US"
    else:
        country = argv[1].capitalize()
    if argv[2] == "":
        module = "bokeh"
    else:
        module = argv[2].lower()

    covid_data = CovidData()
    covid_data.select_country(name=country)
    covid_data.plot_selected_country(name=country, module=module)
