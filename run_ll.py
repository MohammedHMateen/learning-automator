import sqlite3
from datetime import datetime
from time import sleep, time

import numpy as np
import pandas as pd
from playwright.sync_api import sync_playwright

from constants import *
from defaults import *


def quick_toggle_tabs(tab_object_list):
    for tab in tab_object_list:
        tab.bring_to_front()
        for _ in range(MAX_RETRIES):
            if tab.query_selector('div.classroom-media-player'):
                break
            tab.reload()
            sleep(RETRY_SLEEP)
        sleep(QUICK_TOGGLE_SCREEN_SLEEP)


def toggle_tabs(tab_object_list):
    start_time = time()
    cycle_time_seconds = CYCLE_TIME_HOURS * 60 * 60
    # Keep switching tabs every SWITCH_TIME
    while time() - start_time < cycle_time_seconds:
        for tab in tab_object_list:
            tab.bring_to_front()
            sleep(TAB_SWITCH_TIME)
        else:
            quick_toggle_tabs(tab_object_list)


def set_video_playback_settings(page):
    if page.query_selector('div.classroom-media-player'):
        # mute if required
        if page.locator('button.vjs-mute-control>span.vjs-control-text').text_content() == 'Mute':
            page.click('button.vjs-vol-0')
        # set to 2x
        page.click('button.vjs-playback-rate')
        page.click('span:text("2x")')


def shrink_browser(page):
    page.set_viewport_size(VIEWPORT)


def launch_browser_context(playwright):
    browser = playwright.chromium.launch(
        executable_path=CHROME_PATH,
        headless=False,
        ignore_default_args=['--disable-component-update'],
        firefox_user_prefs={"media.gmp-manager.updateEnabled": True,
                            "media.allowed-to-play.enabled": True})
    return browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/91.0.4472.124 Safari/537.36",
        java_script_enabled=True
    )


def close_tabs(tab_object_list):
    for tab in tab_object_list:
        tab.close()


def open_links(watch_url_list: list):
    with sync_playwright() as playwright:
        context = launch_browser_context(playwright)
        cookie_page = context.new_page()
        cookie_page.evaluate("""document.documentElement.requestFullscreen();""")
        context.add_cookies([{
            'name': 'li_at',
            'value': LI_AT_COOKIE,
            'domain': '.www.linkedin.com',  # Ensure this matches the actual domain
            'path': '/'
        }])
        cookie_page.reload()

        # open courses in new tabs
        tab_object_list = []
        for index, url in enumerate(watch_url_list):
            tab_object_list.append(context.new_page())
            tab_object_list[index].goto(url)
            sleep(OPEN_TAB_SLEEP)
            set_video_playback_settings(tab_object_list[index])

        quick_toggle_tabs(tab_object_list)
        shrink_browser(cookie_page)
        cookie_page.close()
        toggle_tabs(tab_object_list)
        close_tabs(tab_object_list)
        context.close()


def get_sheet_id(url):
    return url.split(SHEETS_DOMAIN)[1].split("/")[0]


def load_sheets_df(sheet_id):
    """
    Template for sheet
    url, certified, course_hour
    """
    sheets_csv_link = SHEETS_DOMAIN + sheet_id + SHEETS_EXPORT_PARAM
    sheets_df = pd.read_csv(sheets_csv_link, index_col=0)
    sheets_df = sheets_df[sheets_df[SheetHeader.CERTIFIED.value] != 'Yes']
    sheets_df[SheetHeader.ATTEMPT.value] = 0
    # replace duration nan with default course duration
    sheets_df['course_hour'] = sheets_df['course_hour'].replace([None, '', np.nan], APPROX_COURSE_DURATION_HOURS)
    sheets_df[SheetHeader.MAX_ATTEMPT.value] = sheets_df['course_hour'] // CYCLE_TIME_HOURS
    sheets_df[SheetHeader.MAX_ATTEMPT.value] = sheets_df[SheetHeader.MAX_ATTEMPT.value].clip(upper=5)
    sheets_df[SheetHeader.MAX_ATTEMPT.value] = sheets_df[SheetHeader.MAX_ATTEMPT.value].astype(int)
    sheets_df = sheets_df[[SheetHeader.URL.value, SheetHeader.CERTIFIED.value, SheetHeader.ATTEMPT.value,
                           SheetHeader.MAX_ATTEMPT.value]]
    return sheets_df


def populate_sqlite_db(table_name, sheet_df):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    sheet_df.to_sql(table_name, conn, if_exists='replace', index=False)
    conn.commit()
    conn.close()


def fetch_watch_url_list(table_name):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    url_list_query = (f"select {SheetHeader.URL.value} from `{table_name}` "
                      f"where {SheetHeader.CERTIFIED.value} = '{Status.NO.value}' "
                      f"order by {SheetHeader.MAX_ATTEMPT.value} desc, {SheetHeader.ATTEMPT.value} asc "
                      f"limit {MAX_TABS}")
    cursor.execute(url_list_query)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [row[0] for row in rows]


def increment_attempt(table_name, watch_url_list):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    for watch_url in watch_url_list:
        update_attempt_query = (f"update `{table_name}` "
                                f"set {SheetHeader.ATTEMPT.value} = {SheetHeader.ATTEMPT.value} + 1 "
                                f"where {SheetHeader.URL.value} = '{watch_url}'")
        cursor.execute(update_attempt_query)
    conn.commit()
    cursor.close()
    conn.close()


def delete_maxed_attempts(table_name):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    delete_url_query = (f"delete from `{table_name}` "
                        f"where {SheetHeader.ATTEMPT.value} >= {SheetHeader.MAX_ATTEMPT.value}")
    cursor.execute(delete_url_query)
    conn.commit()
    cursor.close()
    conn.close()


def validate_course_sheet(course_sheet):
    if not course_sheet.startswith(SHEETS_DOMAIN):
        raise KeyError("Invalid Google sheets link")


def update_certified_status(table_name, watch_url_list, status):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    for watch_url in watch_url_list:
        update_attempt_query = (f"update `{table_name}` "
                                f"set {SheetHeader.CERTIFIED.value} = '{status}' "
                                f"where {SheetHeader.URL.value} = '{watch_url}'")
        cursor.execute(update_attempt_query)
    conn.commit()
    cursor.close()
    conn.close()


def get_all_urls_in_db(table_name):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    url_list_query = f"select {SheetHeader.URL.value} from `{table_name}`"
    url_df = pd.read_sql_query(url_list_query, conn)
    conn.close()
    return url_df


def insert_urls(table_name, urls_df_only):
    insert_list = [(url, Status.NO.value, 0, int(max_attempt)) for url, max_attempt in urls_df_only]
    insert_query = (f"INSERT INTO `{table_name}` "
                    f"({SheetHeader.URL.value}, {SheetHeader.CERTIFIED.value}, "
                    f"{SheetHeader.ATTEMPT.value}, {SheetHeader.MAX_ATTEMPT.value}) VALUES (?, ?, ?, ?)")
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    cursor.executemany(insert_query, insert_list)
    conn.commit()
    conn.close()


def delete_urls(table_name, urls_db_only):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    for url in urls_db_only:
        delete_query = (f"DELETE FROM `{table_name}` "
                        f"where {SheetHeader.URL.value} = '{url}'")
        cursor.execute(delete_query)
    conn.commit()
    conn.close()


def refresh_db(table_name, sheets_df):
    """
    !df     db  :   delete the row from DB
    df      !db :   add row in DB certified NO attempt 0
    """
    db_urls_df = get_all_urls_in_db(table_name)
    urls_df_only = list(sheets_df[~sheets_df[SheetHeader.URL.value].isin(db_urls_df[SheetHeader.URL.value])][
                            [SheetHeader.URL.value, SheetHeader.MAX_ATTEMPT.value]].to_records(index=False))
    insert_urls(table_name, urls_df_only)

    urls_db_only = list(db_urls_df[~db_urls_df[SheetHeader.URL.value].isin(sheets_df[SheetHeader.URL.value])][
                            [SheetHeader.URL.value]].to_records(index=False))
    urls_db_only = [url[0] for url in urls_db_only]
    delete_urls(table_name, urls_db_only)


def show_cycle_info(watch_url_list):
    now = datetime.now()
    print(BREAK_LINE)
    print(f"Cycle starting at {now.strftime('%I:%M %p')}\n"
          f"Next Cycle will begin after {CYCLE_TIME_HOURS} hour(s)")
    print(BREAK_LINE)
    print("Opening the following courses:")
    for index, url in enumerate(watch_url_list):
        print(f"{index + 1:0>2}: {url}")
    print(BREAK_LINE)


def run_linkedin_learning_automator():
    try:
        course_sheet = SHEETS_LINK.strip()
        validate_course_sheet(course_sheet)
        sheet_id = get_sheet_id(course_sheet)
        sheet_df = load_sheets_df(sheet_id)
        table_name = "sheet_" + sheet_id[:5] + PROGRESS_SUFFIX
        populate_sqlite_db(table_name, sheet_df)
        watch_url_list = fetch_watch_url_list(table_name)
        while watch_url_list:
            show_cycle_info(watch_url_list.copy())
            update_certified_status(table_name, watch_url_list, Status.IN_PROGRESS.value)
            open_links(watch_url_list)
            increment_attempt(table_name, watch_url_list)
            update_certified_status(table_name, watch_url_list, Status.NO.value)
            delete_maxed_attempts(table_name)
            sheet_df = load_sheets_df(sheet_id)
            refresh_db(table_name, sheet_df)
            watch_url_list = fetch_watch_url_list(table_name)
    except Exception as e:
        print(f"Exception >> {str(e)} \nAutomate another time....\nExiting Cleanly, Bye :)")


if __name__ == "__main__":
    print(BREAK_LINE)
    print(f"Welcome to LinkedIn Learning Automator")
    print("Displaying the defaults (change if required in the defaults file)")
    print(BREAK_LINE)
    print(f"Required Schema:\nurl\tcertified\tduration")
    print(BREAK_LINE)
    print(f"Cycle Time: {CYCLE_TIME_HOURS}\n"
          f"Max Tabs: {MAX_TABS}\n"
          f"Sheets URL: {SHEETS_LINK}\n"
          f"LinkedIn Cookie: {LI_AT_COOKIE}\n"
          f"SQLite DB Path: {SQLITE_DB_PATH}")
    print(BREAK_LINE)
    run_linkedin_learning_automator()
