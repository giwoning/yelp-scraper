import argparse
import time
import random
import logging
import sys
import io
import os
import platform
import traceback
import json
import re
from timeit import default_timer as timer
from datetime import timedelta, datetime

import pandas as pd
from selenium import webdriver
from selenium_stealth import stealth
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

import boto3

import utils

parser = argparse.ArgumentParser()

# Mode Option
parser.add_argument('--collected_object', choices=['restaurant', 'review', 'profile'], required=True)

# Scraper Options
parser.add_argument('--min_index', default=0, type=int)
parser.add_argument('--max_index', default=-1, type=int)
parser.add_argument('--wait_time_for_new_index', default=3, type=int)
parser.add_argument('--additional_wait_time', default=0, type=int)
parser.add_argument('--wait_time_for_next_page_lb', default=10, type=int)
parser.add_argument('--wait_time_for_next_page_ub', default=15, type=int)
parser.add_argument('--index_specified_mode', default=0, type=int)
parser.add_argument('--page_specific_mode', default=0, type=int)
parser.add_argument('--index_for_ps_mode', default=-1, type=int)
parser.add_argument('--part_for_ps_mode', default=0, type=int)

# Log Options
parser.add_argument('--verbose', default=1, type=int)
parser.add_argument('--save_log', default=1, type=int)

# Dataset Option
parser.add_argument('--target_list_name', default='User_List', type=str)

# AWS Options
parser.add_argument('--aws_mode', default=0, type=int)
parser.add_argument('--bucket_name', default='', type=str)

# Chrome Option
parser.add_argument('--open_chrome', default=0, type=int)

# Save Option
parser.add_argument('--index_suffix', default=1, type=int)

args = parser.parse_args()

# Logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

formatter = logging.Formatter('[%(asctime)s][%(levelname)s] >> %(message)s')

if args.save_log:
    fileHandler = logging.FileHandler('./logs/yelp_review_result-' + datetime.now().strftime('%Y_%m_%d-%I_%M_%S_%p')
                                      + '.txt', mode='w', encoding='cp949')
    fileHandler.setFormatter(formatter)
    logger.addHandler(fileHandler)

streamHandler = logging.StreamHandler()
streamHandler.setFormatter(formatter)
logger.addHandler(streamHandler)

success_num = 0
fail_num = 0
fail_list = []
invalid_object_list = []
reviews = {}
profiles = {}
restaurants = {}

class DetectedAsRobotError(Exception):
    def __init__(self):
        super().__init__('Yelp has detected me as ROBOT. Cannot work my job any more.')

def res_scraper(driver, index, res):
    logger.error('In Fixing...')

def profile_scraper(driver, index, reviewer, info_dict):
    logger.info('Current working index: {}, User ID: {}'.format(str(index), reviewer['userid']))
    reset_configuration = False

    url = 'https://www.yelp.com/user_details?userid=' + reviewer['userid']
    max_attempt = 10
    attempt_num = 0
    while attempt_num < max_attempt:
        try:
            driver.get(url)
            if args.additional_wait_time == 0:
                time.sleep(args.wait_time_for_new_index)
            else:
                random_sleep_within_page = random.randint(1, args.additional_wait_time)
                time.sleep(random_sleep_within_page)
            break
        except TimeoutException:
            logger.error('Oops.. Timeout! Reconfiguring webdriver...')
            chrome_options = webdriver.ChromeOptions()
            driver.set_page_load_timeout(10)
            if platform.system() != 'Windows' or args.open_chrome == 0:
                chrome_options.add_argument('--headless')
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('log-level=3')

            driver = webdriver.Chrome(options=chrome_options)
            stealth(driver,
                    languages=["en-US", "en"],
                    vendor="Google Inc.",
                    platform="Win32",
                    webgl_vendor="Intel Inc.",
                    renderer="Intel Iris OpenGL Engine",
                    fix_hairline=True,
                    )
            attempt_num = attempt_num + 1
            logger.info('Done. Attempt #: {}/10'.format(attempt_num))
            reset_configuration = True

    if attempt_num == max_attempt:
        logger.error('Max attempt has reached. Something goes wrong...')
        raise
    
    error_404 = len(driver.find_elements(By.XPATH, './/h1[contains(text(), \"We’re sorry. Something went wrong on this page.\")]')) > 0
    if error_404:
        logger.error('This user page has been removed.')
        invalid_object_list.append(index)
        raise

    cdt_id_name_list = info_dict['cdt_id_name']
    me_list = info_dict['about_me']

    # Profiles
    pi_dict = {}
    pi_dict['user_name'] = ''
    pi_dict['user_loc'] = ''
    pi_dict['user_photo_url'] = ''
    pi_dict['user_friend_num'] = 0
    pi_dict['user_review_num'] = 0
    pi_dict['user_photo_num'] = 0
    pi_dict['user_elite_year'] = 0
    pi_dict['user_tagline'] = ''

    ## Profile Info
    profile_header_element = driver.find_element(By.XPATH, './/div[@data-testid="profile-header-decoration"]/following-sibling::div[1]')

    # 1. Photo
    profile_photo_url_list = []
    user_photo_elements = profile_header_element.find_elements(By.XPATH, "./div[1]/a")
    for photo_element in user_photo_elements:
        photo_url = photo_element.find_element(By.XPATH, './img').get_attribute('src')
        # No photos
        if photo_url.find('default_user_avatar') != -1:
            break
        else:
            profile_photo_url_list.append(photo_url)

    pi_dict['user_photo_url'] = '' if len(profile_photo_url_list) == 0 else ', '.join(profile_photo_url_list)

    # 2. Name
    user_name_element = profile_header_element.find_elements(By.XPATH, './div[2]/a/h2')
    if len(user_name_element) > 0:
        pi_dict['user_name'] = user_name_element[0].text

    # 3. Location
    user_loc_element = profile_header_element.find_elements(By.XPATH, './div[3]/p')
    if len(user_loc_element) > 0:
        pi_dict['user_loc'] = user_loc_element[0].text

    # 4. Passport Stat
    user_stat_elements = profile_header_element.find_elements(By.XPATH, './/div[contains(@class, \"user-passport-stats\")]')
    if len(user_stat_elements) > 0:
            user_friend_element = user_stat_elements[0].find_elements(By.XPATH, './div[@aria-label=\"Friends\"]')
            if len(user_friend_element) > 0:
                pi_dict['user_friend_num'] = int(user_friend_element[0].find_element(By.XPATH, './span[2]/span').text)

            user_review_element = user_stat_elements[0].find_elements(By.XPATH, './div[@aria-label=\"Reviews\"]')
            if len(user_review_element) > 0:
                pi_dict['user_review_num'] = int(user_review_element[0].find_element(By.XPATH, './span[2]/span').text)

            user_photo_element = user_stat_elements[0].find_elements(By.XPATH, './div[@aria-label=\"Photos\"]')
            if len(user_photo_element) > 0:
                pi_dict['user_photo_num'] = int(user_photo_element[0].find_element(By.XPATH, './span[2]/span').text)

    elite_element = profile_header_element.find_elements(By.XPATH,
                                                       ".//a[@href=\"/user_details_years_elite?userid=" + reviewer['userid'] + "\"]")
    if len(elite_element) > 0:
        pi_dict['user_elite_year'] = int(elite_element[0].find_element(By.XPATH, './span').text.split(' ')[1])

    add_friend_element = profile_header_element.find_element(By.XPATH, './/span[text()=\"Add friend\"]')
    user_tagline_element = add_friend_element.find_elements(By.XPATH, '../../preceding-sibling::div[1]/p')
    if len(user_tagline_element) > 0:
        pi_dict['user_tagline'] = user_tagline_element[0].text

    # Impact
    ## Review reactions
    rr_dict = {}
    rr_dict['helpful'] = 0
    rr_dict['thanks'] = 0
    rr_dict['love_this'] = 0
    rr_dict['oh_no'] = 0
    review_reaction_elements = driver.find_elements(By.XPATH, './/p[text()="Review reactions"]')
    if len(review_reaction_elements) > 0:
        helpful_element = review_reaction_elements[0].find_elements(By.XPATH,
                                                                    '../following-sibling::div/div[1]/div/div[2]/p[2]')
        if len(helpful_element) > 0:
            rr_dict['helpful'] = helpful_element[0].text
        thanks_element = review_reaction_elements[0].find_elements(By.XPATH,
                                                                   '../following-sibling::div[1]/div[2]/div/div[2]/p[2]')
        if len(thanks_element) > 0:
            rr_dict['thanks'] = thanks_element[0].text
        love_this_element = review_reaction_elements[0].find_elements(By.XPATH,
                                                                      '../following-sibling::div[1]/div[3]/div/div[2]/p[2]')
        if len(love_this_element) > 0:
            rr_dict['love_this'] = love_this_element[0].text
        oh_no_element = review_reaction_elements[0].find_elements(By.XPATH,
                                                                  '../following-sibling::div[1]/div[4]/div/div[2]/p[2]')
        if len(oh_no_element) > 0:
            rr_dict['oh_no'] = oh_no_element[0].text

    ## Stats
    stat_dict = {}
    stat_dict['review_updates'] = 0
    stat_dict['first_reviews'] = 0
    stat_dict['followers'] = 0
    stat_elements = driver.find_elements(By.XPATH, './/p[text()="Stats"]')
    if len(stat_elements) > 0:
        review_updates_element = stat_elements[0].find_elements(By.XPATH,
                                                                '../following-sibling::div[1]/div[1]/div/div[2]/p[2]')
        if len(review_updates_element) > 0:
            stat_dict['review_updates'] = review_updates_element[0].text
        first_reviews_element = stat_elements[0].find_elements(By.XPATH,
                                                               '../following-sibling::div[1]/div[2]/div/div[2]/p[2]')
        if len(first_reviews_element) > 0:
            stat_dict['first_reviews'] = first_reviews_element[0].text
        followers_element = stat_elements[0].find_elements(By.XPATH,
                                                           '../following-sibling::div[1]/div[3]/div/div[2]/p[2]')
        if len(followers_element) > 0:
            stat_dict['followers'] = followers_element[0].text

    ## Compliments
    compliments_dict = {}
    for id_name in cdt_id_name_list:
        compliments_dict[id_name] = 0
    child_compliments_elements = driver.find_elements(By.XPATH, './/p[text()="Compliments"]')
    if len(child_compliments_elements) > 0:
            this_compliment_element = driver.find_elements(By.XPATH,
                                                           ".//div[@data-testid=\"impact-compliment-" + id_name + "\"]")
            if len(this_compliment_element) > 0:
                compliments_dict[id_name] = int(this_compliment_element[0].find_element(By.XPATH,
                                                                                        './div/span[2]/span[2]').text)

    # Review Distribution
    ## Ratings
    rd_dict = {}
    rd_dict['s5'] = 0
    rd_dict['s4'] = 0
    rd_dict['s3'] = 0
    rd_dict['s2'] = 0
    rd_dict['s1'] = 0
    rating_elements = driver.find_elements(By.XPATH, './/p[text()="Ratings"]')
    if len(rating_elements) > 0:
        s5_element = rating_elements[0].find_elements(By.XPATH,
                                                      '../following-sibling::div[1]/div/div[1]/div/div[2]/div')
        if len(s5_element) > 0:
            match = re.search(r'\((.*?)\)', s5_element[0].get_attribute('aria-label'))
            if match:
                rd_dict['s5'] = int(match.group(1))

        s4_element = rating_elements[0].find_elements(By.XPATH,
                                                      '../following-sibling::div[1]/div/div[2]/div/div[2]/div')
        if len(s4_element) > 0:
            match = re.search(r'\((.*?)\)', s4_element[0].get_attribute('aria-label'))
            if match:
                rd_dict['s4'] = int(match.group(1))

        s3_element = rating_elements[0].find_elements(By.XPATH,
                                                      '../following-sibling::div[1]/div/div[3]/div/div[2]/div')
        if len(s3_element) > 0:
            match = re.search(r'\((.*?)\)', s3_element[0].get_attribute('aria-label'))
            if match:
                rd_dict['s3'] = int(match.group(1))

        s2_element = rating_elements[0].find_elements(By.XPATH,
                                                      '../following-sibling::div[1]/div/div[4]/div/div[2]/div')
        if len(s2_element) > 0:
            match = re.search(r'\((.*?)\)', s2_element[0].get_attribute('aria-label'))
            if match:
                rd_dict['s2'] = int(match.group(1))

        s1_element = rating_elements[0].find_elements(By.XPATH,
                                                      '../following-sibling::div[1]/div/div[5]/div/div[2]/div')
        if len(s1_element) > 0:
            match = re.search(r'\((.*?)\)', s1_element[0].get_attribute('aria-label'))
            if match:
                rd_dict['s1'] = int(match.group(1))

    ## Top categories
    top5_dict = {}
    top1_name = ''
    top1_num = 0
    top2_name = ''
    top2_num = 0
    top3_name = ''
    top3_num = 0
    top4_name = ''
    top4_num = 0
    top5_name = ''
    top5_num = 0
    child_tc_elements = driver.find_elements(By.XPATH, './/p[text()="Top categories"]')
    if len(child_tc_elements) > 0:
        tc_elements = child_tc_elements[0].find_elements(By.XPATH, '../following-sibling::ul/li')
        if len(tc_elements) > 0:
            for this_c in tc_elements:
                cat_name_and_num = this_c.find_element(By.XPATH, './p').text
                name_end_idx = cat_name_and_num.find('(')
                cat_name = cat_name_and_num[:name_end_idx].strip()
                cat_num = cat_name_and_num[name_end_idx + 1:-1]
                top5_dict[cat_name] = cat_num

    for i, (key, value) in enumerate(top5_dict.items()):
        if i == 0:
            top1_name = key
            top1_num = int(value)
        if i == 1:
            top2_name = key
            top2_num = int(value)
        if i == 2:
            top3_name = key
            top3_num = int(value)
        if i == 3:
            top4_name = key
            top4_num = int(value)
        if i == 4:
            top5_name = key
            top5_num = int(value)

    ## More about me
    me_dict = {}
    for me_info in me_list:
        me_dict[me_info] = ''
    show_more_text_element = driver.find_elements(By.XPATH, './/p[text()="Show more"]')
    if len(show_more_text_element) > 0:
        button = show_more_text_element[0].find_element(By.XPATH, 'ancestor::button[1]')
        time.sleep(0.1)
        button.click()

    me_title_element = driver.find_elements(By.XPATH, './/h3[text()="More about me"]')
    if len(me_title_element) > 0:
        if len(show_more_text_element) > 0:
            me_info_elements = me_title_element[0].find_elements(By.XPATH, '../following-sibling::div[1]/div/div/div')
        else:
            me_info_elements = me_title_element[0].find_elements(By.XPATH, '../following-sibling::div[1]/div')
        if len(me_info_elements) > 0:
            for me_info in me_list:
                this_me_info_element = me_info_elements[0].find_elements(By.XPATH, ".//p[text()=\"" + me_info + "\"]")
                if len(this_me_info_element) > 0:
                    me_dict[me_info] = this_me_info_element[0].find_element(By.XPATH, './following-sibling::p').text

    location = me_dict['Location']
    yelping_since = me_dict['Yelping since']
    things_i_love = me_dict['Things I Love']
    find_me_in = me_dict['Find Me In']
    my_hometown = me_dict['My Hometown']
    my_blog_or_website = me_dict['My Blog Or Website']
    when_im_not_yelping = me_dict['When I’m Not Yelping...']
    why_ysrmr = me_dict['Why You Should Read My Reviews']
    my_second_fw = me_dict['My Second Favorite Website']
    last_great_book = me_dict['The Last Great Book I Read']
    my_first_concert = me_dict['My First Concert']
    my_favorite_movie = me_dict['My Favorite Movie']
    my_last_meal_on_earth = me_dict['My Last Meal On Earth']
    dont_tell_anyone_else_but = me_dict['Don’t Tell Anyone Else But...']
    most_recent_discovery = me_dict['Most Recent Discovery']
    current_crush = me_dict['Current Crush']

    this_profile = [reviewer['userid'], pi_dict['user_name'], pi_dict['user_loc'], pi_dict['user_photo_url'],
                    pi_dict['user_friend_num'], pi_dict['user_review_num'], pi_dict['user_photo_num'],
                    pi_dict['user_elite_year'], pi_dict['user_tagline'],
                    rd_dict['s5'], rd_dict['s4'], rd_dict['s3'], rd_dict['s2'], rd_dict['s1'],
                    rr_dict['helpful'], rr_dict['thanks'], rr_dict['love_this'], rr_dict['oh_no'],
                    stat_dict['review_updates'], stat_dict['first_reviews'], stat_dict['followers'],
                    top1_name, top1_num, top2_name, top2_num, top3_name, top3_num,
                    top4_name, top4_num, top5_name, top5_num,
                    compliments_dict['thankYou'], compliments_dict['cutePic'], compliments_dict['goodWriter'],
                    compliments_dict['hotStuff'], compliments_dict['justANote'], compliments_dict['ilikeYourProfile'],
                    compliments_dict['writeMore'], compliments_dict['youAreCool'], compliments_dict['greatPhoto'],
                    compliments_dict['greatList'], compliments_dict['youAreFunny'],
                    me_dict['Location'], me_dict['Yelping since'], me_dict['Things I Love'], me_dict['Find Me In'],
                    me_dict['My Hometown'], me_dict['My Blog Or Website'], me_dict['When I’m Not Yelping...'],
                    me_dict['Why You Should Read My Reviews'], me_dict['My Second Favorite Website'],
                    me_dict['The Last Great Book I Read'], me_dict['My First Concert'], me_dict['My Favorite Movie'],
                    me_dict['My Last Meal On Earth'], me_dict['Don’t Tell Anyone Else But...'],
                    me_dict['Most Recent Discovery'], me_dict['Current Crush']]
    profiles[index] = this_profile
    return reset_configuration

def review_scraper(driver, index, res, list_of_page=[]):
    previous_sleep_time = -1
    previous_sleep_time_within_page = -1

    yelpid_list = []
    yelp_name_list = []
    user_name_list = []
    user_id_list = []
    user_elite_list = []
    user_first_review_list = []
    user_loc_list = []
    user_friend_num_list = []
    user_review_num_list = []
    user_photos_num_list = []
    rating_list = []
    date_list = []
    user_review_updated_list = []
    user_num_posted_photo_list = []
    user_num_check_ins_list = []
    comment_list = []
    helpful_list = []
    thanks_list = []
    love_this_list = []
    oh_no_list = []
    owner_comment_date_list = []
    owner_comment_list = []
    previous_ratings_list = []
    previous_datess_list = []
    previous_comments_list = []
    previous_helpfuls_list = []
    previous_thankss_list = []
    previous_love_thiss_list = []
    previous_oh_nos_list = []

    yelpid = res['yelpid']
    yelp_name = res['name']
    yelp_url = res['scrapedurl']
    if len(list_of_page) > 0 and args.part_for_ps_mode > 1:
        start_page = list_of_page.pop()
        driver.get(yelp_url + start_page)
    else:
        driver.get(yelp_url)

    detected_as_robot = driver.find_elements(By.XPATH, './/h2[contains(text(), "Hey there! Before you continue")]')
    if len(detected_as_robot) > 0:
        raise DetectedAsRobotError
    random_sleep = random.randint(3, args.wait_time_for_new_index)
    while random_sleep == previous_sleep_time:
        random_sleep = random.randint(3, time.sleep(args.wait_time_for_new_index))
    time.sleep(random_sleep)
    previous_sleep_time = random_sleep

    start = timer()
    logger.info('Index: {}. Yelp ID: {}'.format(index, yelpid))
    navigation_elements = driver.find_elements(By.XPATH, './/div[@aria-label="Pagination navigation"]')
    total_page = 0
    if len(navigation_elements) > 0:
        total_page = int(navigation_elements[0].find_elements(By.XPATH, './div[2]/span')[0].text.split('of')[1])

    if args.page_specific_mode == 0:
        if total_page > 1:
            list_of_page = ['?start=' + str(i * 10) for i in random.sample(range(1, total_page), total_page - 1)]
    loaded_page_num = len(list_of_page) + 1
    total_review_num = 0
    page = 0
    while (True):
        page = page + 1
        retried = False
        if page == 1:
            if args.page_specific_mode == 1 and args.part_for_ps_mode > 1:
                logger.info(
                    'Current Index: {}, Page: 1 / {}, Acutal Page: {}'.format(str(index), str(loaded_page_num), start_page))
            else:
                logger.info('Current Index: {}, Page: 1 / {}, Acutal Page: Home'.format(str(index), str(loaded_page_num)))
        else:
            current_page = list_of_page.pop()
            logger.info(
                'Current Index: {}, Page: {} / {}, Acutal Page: {}'.format(str(index), str(page), str(loaded_page_num), current_page))
            
            attempts = 0
            while (attempts < 10):
                try:
                    driver.get(yelp_url + current_page)
                    random_sleep_within_page = random.randint(args.wait_time_for_next_page_lb, args.wait_time_for_next_page_ub)
                    while random_sleep_within_page == previous_sleep_time_within_page:
                        random_sleep_within_page = random.randint(args.wait_time_for_next_page_lb, args.wait_time_for_next_page_ub)
                    time.sleep(random_sleep_within_page)
                    previous_sleep_time_within_page = random_sleep_within_page
                    navigation_elements = driver.find_element(By.XPATH, './/div[@aria-label="Pagination navigation"]')
                    break
                except TimeoutException:
                    attempts = attempts + 1
                    logger.error('Failed to load the page... Refreshing... {}/10'.format(attempts))
            
            if attempts == 10:
                logger.error('Exceed max attempts... Something happens..')
                raise
            
            current_page_num = int(navigation_elements.find_elements(By.XPATH, './div[2]/span')[0].text.split('of')[0])
            this_total_page_num = int(
                navigation_elements.find_elements(By.XPATH, './div[2]/span')[0].text.split('of')[1])
            if current_page_num > this_total_page_num:
                logger.info('This page number is larger than total page number. Continue to next page...')
                continue
    
        review_elements_f = driver.find_elements(By.XPATH, './/section[@aria-label="Recommended Reviews"]')
        if len(review_elements_f) == 0:
            logger.info('Oops.. Something goes wrong.. Reloading the page...')
            if page > 1:
                driver.get(yelp_url + current_page)
            else:
                driver.get(yelp_url)
            random_sleep_within_page = random.randint(args.wait_time_for_next_page_lb, args.wait_time_for_next_page_ub)
            while random_sleep_within_page == previous_sleep_time_within_page:
                random_sleep_within_page = random.randint(args.wait_time_for_next_page_lb,
                                                          args.wait_time_for_next_page_ub)
            time.sleep(random_sleep_within_page)
            previous_sleep_time_within_page = random_sleep_within_page

            review_elements_f = driver.find_elements(By.XPATH, './/section[@aria-label="Recommended Reviews"]')
            if len(review_elements_f) == 0:
                logger.info('Bad... Moving to next...')
                break
            else:
                review_elements = review_elements_f[0].find_elements(By.XPATH, './div[2]/ul/li')
                num_loaded_reviews = len(review_elements)
                if num_loaded_reviews == 0:
                    logger.info('No reviews... Moving to next...')
                    break
        else:
            review_elements = review_elements_f[0].find_elements(By.XPATH, './div[2]/ul/li')
            num_loaded_reviews = len(review_elements)
            if num_loaded_reviews == 0:
                logger.info('No reviews... Moving to next...')
                break

        total_review_num = total_review_num + num_loaded_reviews
        for review_element in review_elements:
            read_more_elements = review_element.find_elements(By.XPATH, './/button')
            for read_more_button in read_more_elements:
                time.sleep(0.1)
                read_more_button.click()

            user_info_element = review_element.find_element(By.XPATH, './/div[contains(@class, "user-passport-info")]')
            user_name = user_info_element.find_element(By.XPATH, './span/a').text
            user_id = user_info_element.find_element(By.XPATH, './span/a').get_attribute('href').split('?')[1].replace(
                'userid=', '')
            user_elite_element = user_info_element.find_elements(By.XPATH, './/div[contains(@class, "elite-badge")]')
            if len(user_elite_element) > 0:
                user_elite = 1
                user_loc_element = user_info_element.find_elements(By.XPATH, './div[2]/div/span')
                if len(user_loc_element) > 0:
                    user_loc = user_loc_element[0].text
                else:
                    user_loc = ''
            else:
                user_elite = 0
                user_loc_element = user_info_element.find_elements(By.XPATH, './div/div/span')
                if len(user_loc_element) > 0:
                    user_loc = user_loc_element[0].text
                else:
                    user_loc = ''
            first_review_element = review_element.find_elements(By.XPATH, './/span[contains(text(), "First to Review")]')
            user_first_review = 1 if len(first_review_element) > 0 else 0
            # User Passport Stat
            passport_stat = {}
            passport_stat['Friends'] = 0
            passport_stat['Reviews'] = 0
            passport_stat['Photos'] = 0
            user_passport_elements = review_element.find_element(By.XPATH,
                                                                 './/div[contains(@class, "user-passport-stat")]').find_elements(
                By.XPATH, './div')
            for stat_element in user_passport_elements:
                passport_stat[stat_element.get_attribute('aria-label')] = int(
                    stat_element.find_element(By.XPATH, './span[2]/span').text)

            rating_and_date_element = review_element.find_element(By.XPATH,
                                                                  './/div[contains(@aria-label, "star rating")]')
            rating = int(rating_and_date_element.get_attribute('aria-label').split(' ')[0])
            date = rating_and_date_element.find_element(By.XPATH, '../../following-sibling::div[1]').find_element(
                By.XPATH, './span').text

            updated_element = review_element.find_elements(By.XPATH, './/span[contains(text(), "Updated review")]')
            if len(updated_element) > 0:
                user_review_updated = 1
            else:
                user_review_updated = 0

            user_num_posted_photo_elements = review_element.find_elements(By.XPATH,
                                                                          './/a[contains(@href, "biz_photos")]')
            if len(user_num_posted_photo_elements) > 0:
                if user_num_posted_photo_elements[0].text.find('See all photos from') != -1:
                    user_num_posted_photo = 0
                else:
                    user_num_posted_photo = int(re.sub(r'[^0-9]', '', user_num_posted_photo_elements[0].text))
            else:
                user_num_posted_photo = 0

            user_num_check_ins_element = review_element.find_elements(By.XPATH,
                                                                      './/span[text()="check-ins"]')
            if len(user_num_check_ins_element) > 0:
                user_num_check_ins = int(re.sub(r'[^0-9]', '', user_num_check_ins_element[0].text))
            else:
                user_num_check_ins = 0

            comment_elements = review_element.find_elements(By.XPATH, './/p[contains(@class, "comment")]')
            comment_elements.reverse()
            # first comment element is this reviewer's comment.
            comment_element = comment_elements.pop()
            comment = comment_element.find_element(By.XPATH, './span').text

            helpful = int(re.sub(r'[^0-9]', '', review_element.find_element(By.XPATH,
                                                                            './/div[contains(@aria-label, "Helpful")]').get_attribute(
                'aria-label')))
            thanks = int(re.sub(r'[^0-9]', '', review_element.find_element(By.XPATH,
                                                                           './/div[contains(@aria-label, "Thanks")]').get_attribute(
                'aria-label')))
            love_this = int(re.sub(r'[^0-9]', '', review_element.find_element(By.XPATH,
                                                                              './/div[contains(@aria-label, "Love this")]').get_attribute(
                'aria-label')))
            oh_no = int(re.sub(r'[^0-9]', '', review_element.find_element(By.XPATH,
                                                                          './/div[contains(@aria-label, "Oh no")]').get_attribute(
                'aria-label')))

            owner_comment = ''
            owner_comment_date = ''
            previous_ratings = ''
            previous_dates = ''
            previous_comments = ''
            previous_helpfuls = ''
            previous_thankss = ''
            previous_love_thiss = ''
            previous_oh_nos = ''
            previous_rating_list = []
            previous_dates_list = []
            previous_comment_list = []
            previous_helpful_list = []
            previous_thanks_list = []
            previous_love_this_list = []
            previous_oh_no_list = []
            # More than one comment: Owner's reply or previous comments.
            # Second comment element is owner comment if exist
            if len(comment_elements) > 0:
                if len(review_element.find_elements(By.XPATH,
                                                    './/div[contains(@aria-labelledby, "businessOwner")]')) > 0:
                    owner_comment_element = comment_elements.pop()
                    owner_comment = owner_comment_element.find_element(By.XPATH, './span').text
                    owner_comment_date = owner_comment_element.find_element(By.XPATH, './preceding-sibling::div/p').text

                if len(comment_elements) > 0:
                    for previous_comment_element in comment_elements:
                        previous_comment = previous_comment_element.find_element(By.XPATH, './span').text

                        previous_rating_and_date_element = previous_comment_element.find_element(By.XPATH,
                                                                                                 '../../../../preceding-sibling::div[1]/div[1]/div/div')
                        previous_rating = re.sub(r'[^0-9]', '', previous_rating_and_date_element.find_element(By.XPATH,
                                                                                                              './div[1]/span/div').get_attribute(
                            'aria-label'))
                        previous_date = previous_rating_and_date_element.find_element(By.XPATH, './div[2]/span[1]').text
                        if len(previous_comment_element.find_element(By.XPATH,
                                                                     '../following-sibling::div[1]').find_elements(
                                By.XPATH, './/span[contains(text(), "Helpful")]')) > 0:
                            previous_comment_helpfuls = previous_comment_element.find_elements(By.XPATH,
                                                                                               '../following-sibling::div[1]/div/div/div')
                        else:
                            previous_comment_helpfuls = previous_comment_element.find_elements(By.XPATH,
                                                                                               '../following-sibling::div[2]/div/div/div')

                        previous_helpful = (re.sub(r'[^0-9]', '', previous_comment_helpfuls[0].find_element(By.XPATH,
                                                                                                            './div').get_attribute(
                            'aria-label')))
                        previous_thanks = (re.sub(r'[^0-9]', '', previous_comment_helpfuls[1].find_element(By.XPATH,
                                                                                                           './div').get_attribute(
                            'aria-label')))
                        previous_love_this = (re.sub(r'[^0-9]', '', previous_comment_helpfuls[2].find_element(By.XPATH,
                                                                                                              './div').get_attribute(
                            'aria-label')))
                        previous_oh_no = (re.sub(r'[^0-9]', '', previous_comment_helpfuls[3].find_element(By.XPATH,
                                                                                                          './div').get_attribute(
                            'aria-label')))

                        previous_comment_list.append(previous_comment)
                        previous_rating_list.append(previous_rating)
                        previous_dates_list.append(previous_date)

                        previous_helpful_list.append(previous_helpful)
                        previous_thanks_list.append(previous_thanks)
                        previous_love_this_list.append(previous_love_this)
                        previous_oh_no_list.append(previous_oh_no)

                    previous_ratings = ', '.join(previous_rating_list)
                    previous_dates = ', '.join(previous_dates_list)
                    previous_comments = ', '.join(previous_comment_list)
                    previous_helpfuls = ', '.join(previous_helpful_list)
                    previous_thankss = ', '.join(previous_thanks_list)
                    previous_love_thiss = ', '.join(previous_love_this_list)
                    previous_oh_nos = ', '.join(previous_oh_no_list)

            yelpid_list.append(yelpid)
            yelp_name_list.append(yelp_name)
            user_name_list.append(user_name)
            user_id_list.append(user_id)
            user_elite_list.append(user_elite)
            user_first_review_list.append(user_first_review)
            user_loc_list.append(user_loc)
            user_friend_num_list.append(passport_stat['Friends'])
            user_review_num_list.append(passport_stat['Reviews'])
            user_photos_num_list.append(passport_stat['Photos'])
            rating_list.append(rating)
            date_list.append(date)
            user_review_updated_list.append(user_review_updated)
            user_num_posted_photo_list.append(user_num_posted_photo)
            user_num_check_ins_list.append(user_num_check_ins)
            comment_list.append(comment)
            helpful_list.append(helpful)
            thanks_list.append(thanks)
            love_this_list.append(love_this)
            oh_no_list.append(oh_no)
            owner_comment_date_list.append(owner_comment_date)
            owner_comment_list.append(owner_comment)
            previous_ratings_list.append(previous_ratings)
            previous_datess_list.append(previous_dates)
            previous_comments_list.append(previous_comments)
            previous_helpfuls_list.append(previous_helpfuls)
            previous_thankss_list.append(previous_thankss)
            previous_love_thiss_list.append(previous_love_thiss)
            previous_oh_nos_list.append(previous_oh_nos)

        if len(list_of_page) == 0:
            end = timer()
            global reviews
            logger.info("[{}]: Done. {} reivews have been collected.".format(yelpid, total_review_num))
            logger.info('Elapsed Time: ' + str(timedelta(seconds=(end - start))))
            this_reviews = [yelpid_list, yelp_name_list, user_name_list, user_id_list, user_elite_list,
                            user_first_review_list, user_loc_list, user_friend_num_list, user_review_num_list,
                            user_photos_num_list, rating_list, date_list, user_review_updated_list,
                            user_num_posted_photo_list, user_num_check_ins_list, comment_list, helpful_list,
                            thanks_list, love_this_list, oh_no_list, owner_comment_date_list, owner_comment_list,
                            previous_ratings_list, previous_datess_list, previous_comments_list, previous_helpfuls_list,
                            previous_thankss_list, previous_love_thiss_list, previous_oh_nos_list]
            reviews[index] = this_reviews
            break

def main(args, obj):
    chrome_options = webdriver.ChromeOptions()
    if platform.system() != 'Windows' or args.open_chrome == 0:
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('log-level=3')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

    if platform.system() == 'Windows':
        driver = webdriver.Chrome(options=chrome_options)
    else:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.set_page_load_timeout(10)
    stealth(driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
            )
    # Load restaurant list file.
    if args.aws_mode:
        yelp_target_df = pd.read_csv(io.BytesIO(obj['Body'].read()))
    else:
        yelp_target_df = pd.read_csv(args.target_list_name + '.csv', encoding='utf-8')

    object_name = ""
    if args.collected_object == 'profile':
        if (not 'user_id' in yelp_target_df.columns) and (not 'userid' in yelp_target_df.columns):
            logger.error('Cannot find user_id column in your list file. The program will be terminated.')
            exit()
        object_name = "user"
    else:
        if (not 'yelp_id' in yelp_target_df.columns) and (not 'yelpid' in yelp_target_df.columns):
            logger.error('Cannot find yelp_id column in your list file. The program will be terminated.')
            exit()
        object_name = "restaurant"



    if args.index_specified_mode:
        index_set = sorted(utils.load_specific_mode_file('index_set.txt'))
        list_of_page = []
        if not utils.check_index_list(index_set, len(yelp_target_df) - 1):
            logger.error('Check your index_set.txt. It may contains invalid indices. The program will be terminated.')
            exit()

    elif args.page_specific_mode:
        index_set = [args.index_for_ps_mode]
        total_list_of_page = utils.load_specific_mode_file(str(args.index_for_ps_mode) + '_page_list.txt', True)

        if not utils.check_page_list(total_list_of_page):
            logger.error('Check your ' + str(args.index_for_ps_mode) + '_page_list.text. The program will be terminated.')
            exit()

        if not isinstance(args.part_for_ps_mode, int):
            logger.error('You must the integer number for part argument. The program will be terminated.')
            exit()

        if not (args.part_for_ps_mode >= 1 and args.part_for_ps_mode <= 10):
            logger.error('Part argument is out of ragne. It must be between 1 to 10, inclusive. The program will be terminated.')
            exit()

        unit = len(total_list_of_page) / 10
        start_idx = int((args.part_for_ps_mode - 1) * (unit)) + (args.part_for_ps_mode > 1)
        end_idx = int(args.part_for_ps_mode * unit) if args.part_for_ps_mode != 10 else len(total_list_of_page) - 1
        list_of_page = total_list_of_page[start_idx:end_idx + 1]
        logger.info('Page specific mode is successfully activated.')
        logger.info('Target index: {}, Start page index: {}, End page index: {}'.format(args.index_for_ps_mode, start_idx, end_idx))

    else:
        # Check max index
        if args.max_index == -1:
            max_index = len(yelp_target_df) - 1
        else:
            if args.max_index > len(yelp_target_df) - 1:
                logger.warning('Max index is too large. It is set to the last index ' + str(len(yelp_target_df) - 1) + '.')
                max_index = len(yelp_target_df) - 1
            else:
                max_index = args.max_index
        index_set = list(range(args.min_index, max_index + 1, 1))
        list_of_page = []

    if args.verbose:
        logger.info('The target list file has been successfully loaded.')
        logger.info('The total number of ' + object_name + 's is ' + str(len(yelp_target_df)) + '.')

    target_obj_num = len(index_set)
    yelp_target_df = yelp_target_df.loc[index_set]
    if args.verbose:
        logger.info('The number of target ' + object_name + 's is ' + str(target_obj_num))

    start = timer()
    required_info_dict = {}
    if args.collected_object == 'profile':
        cdt_id_name_list = ['thankYou', 'justANote', 'greatPhoto', 'goodWriter', 'ilikeYourProfile', 'justANote',
                            'writeMore', 'youAreCool', 'cutePic', 'greatList', 'youAreFunny', 'hotStuff']
        me_list = ['Location', 'Yelping since', 'Things I Love', 'Find Me In', 'My Hometown', 'My Blog Or Website',
                   'When I’m Not Yelping...', 'Why You Should Read My Reviews', 'My Second Favorite Website',
                   'The Last Great Book I Read', 'My First Concert', 'My Favorite Movie', 'My Last Meal On Earth',
                   'Don’t Tell Anyone Else But...', 'Most Recent Discovery', 'Current Crush']
        required_info_dict['cdt_id_name'] = cdt_id_name_list
        required_info_dict['about_me'] = me_list

    while(True):
        global success_num, fail_num
        if len(index_set) == 0:
            break

        try:
            for index, object in yelp_target_df.iterrows():
                if args.collected_object == 'profile':
                    reset_configuration = profile_scraper(driver, index, object, required_info_dict)
                    if reset_configuration:
                        chrome_options = webdriver.ChromeOptions()
                        driver.set_page_load_timeout(10)
                        if platform.system() != 'Windows' or args.open_chrome == 0:
                            chrome_options.add_argument('--headless')
                            chrome_options.add_argument('--no-sandbox')
                            chrome_options.add_argument('--disable-dev-shm-usage')
                        chrome_options.add_argument('log-level=3')

                        driver = webdriver.Chrome(options=chrome_options)
                        stealth(driver,
                                languages=["en-US", "en"],
                                vendor="Google Inc.",
                                platform="Win32",
                                webgl_vendor="Intel Inc.",
                                renderer="Intel Iris OpenGL Engine",
                                fix_hairline=True,
                                )
                elif args.collected_object == 'review':
                    review_scraper(driver, index, object, list_of_page)
                else:
                    res_scraper(driver, index, object)
                success_num += 1
                index_set.pop(0)
        except:
            fail_num += 1
            error_index = index_set.pop(0)
            if not error_index in invalid_object_list:
                fail_list.append(error_index)
            logger.error(sys.exc_info()[0])
            logger.error(traceback.format_exc())
            logger.error('Index ' + str(error_index) +': Error occured. This ' + object_name + ' gets skipped.')
            if len(index_set) > 0:
                yelp_target_df = yelp_target_df.loc[index_set]

    logger.info('-----------------')
    logger.info('Report')
    logger.info('Total Number of Targets: ' + str(target_obj_num))
    logger.info('Success: ' + str(success_num))
    logger.info('Fail: ' + str(fail_num))
    if fail_num > 0:
        msg = ", ".join(map(str, fail_list))
        logger.info('Failed Indexs: ' + msg)
        if len(invalid_object_list) > 0:
            msg2 = ', '.join(map(str, invalid_object_list))
            logger.info('The following ' + object_name + 's has no information: ' + msg2)
    logger.info('-----------------')

    if success_num == 0:
        logger.info('Nothing to save because NO DATA HAVE BEEN COLLECTED :(')

    else:
        logger.info('Saving the result...')
        global reviews, profiles, restaurants
        if args.collected_object == 'profile':
            results = utils.set_to_df(profiles, 'profile')
        elif args.collected_object == 'review':
            results = utils.set_to_df(reviews, 'review')
        else:
            results = utils.set_to_df(restaurants, 'restaurant')

        if args.collected_object == 'profile':
            file_name = 'yelp_profile.csv'
        elif args.collected_object == 'review':
            file_name = 'yelp_review.csv'
        else:
            file_name = 'yelp_res_info.csv'

        if args.index_suffix:
            if args.index_specified_mode:
                if args.collected_object == 'profile':
                    file_name = 'yelp_profile_index_specified (' + str(success_num) + ' of ' + str(target_obj_num) + ' users).csv'
                elif args.collected_object == 'review':
                    file_name = 'yelp_review_index_specified (' + str(success_num) + ' of ' + str(target_obj_num) + ' reviews).csv'
                else:
                    file_name = 'yelp_res_info_index_specified (' + str(success_num) + ' of ' + str(target_obj_num) + ' reviews).csv'
            elif args.page_specific_mode:
                file_name = 'yelp_review_page_specified (from ' + str(start_idx) + ' to ' + str(end_idx) + ' of ' + str(args.index_for_ps_mode) + ' reviews).csv'
            else:
                if fail_num == 0:
                    if args.collected_object == 'profile':
                        file_name = 'yelp_profile_from_' + str(args.min_index) + '_to_' + str(max_index) + '.csv'
                    elif args.collected_object == 'review':
                        file_name = 'yelp_review_from_' + str(args.min_index) + '_to_' + str(max_index) + '.csv'
                    else:
                        file_name = 'yelp_res_info_from_' + str(args.min_index) + '_to_' + str(max_index) + '.csv'
                else:
                    if args.collected_object == 'profile':
                        file_name = 'yelp_profile_from_' + str(args.min_index) + '_to_' + str(max_index) + \
                                    ' (' + str(fail_num) + ' fails).csv'
                    elif args.collected_object == 'review':
                        file_name = 'yelp_review_from_' + str(args.min_index) + '_to_' + str(max_index) + \
                                ' (' + str(fail_num) + ' fails).csv'
                    else:
                        file_name = 'yelp_res_info_' + str(args.min_index) + '_to_' + str(max_index) + \
                                ' (' + str(fail_num) + ' fails).csv'
        end = timer()
        if args.aws_mode:
            with io.StringIO() as csv_buffer:
                results.to_csv(csv_buffer, index=False)
                response = s3.put_object(Bucket=args.bucket_name, Key=file_name, Body=csv_buffer.getvalue())
                status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
                if status == 200:
                    logger.info(
                        'Done. All work you requested has been finished. The program will be terminated.')
                else:
                    logger.error('Failed to save the result file to your S3 bucket.')
        else:
            results.to_csv(file_name, encoding='utf-8', index=False)
            logger.info('Done. All work you requested has been finished. The program will be terminated.')
        logger.info('Total Elapsed Time: ' + str(timedelta(seconds=(end - start))))

if __name__ == '__main__':
    parser_error = False
    # args check
    if args.index_specified_mode:
        if not os.path.exists('index_list.txt'):
            logger.error('index_list.txt cannot be found.')
            exit()

        if len(utils.load_specific_mode_file('index_list.txt')) == 0:
            logger.error('index_list.txt is empty or invalid.')
            exit()

    else:
        if args.min_index < 0:
            parser_error = True
            parser.error('Min index cannot be negative.')

        if args.max_index != -1 & args.max_index < 0:
            parser_error = True
            parser.error('Max index must be -1 or non-negative.')

        if (args.max_index != -1) & (args.min_index > args.max_index):
            parser_error = True
            parser.error('Min index cannot be larger than max index.')

    if args.wait_time_for_new_index < 0:
        parser_error = True
        parser.error('Wait time for new index cannot be negative.')

    if args.wait_time_for_next_page_lb < 0 or args.wait_time_for_next_page_ub < 0:
        parser_error = True
        parser.error('Wait time for next page cannot be negative.')

    if parser_error:
        logger.error('Some arguments you entered are not valid.')
        exit()

    # file existence check
    obj = None
    if args.aws_mode:
            prefix = args.target_list_name + '.csv'
            try:
                s3 = boto3.client('s3')
            except:
                print('Cannot access your AWS S3 service. Check your IAM role.')
                exit()
            else:
                try:
                    obj = s3.get_object(Bucket=args.bucket_name, Key=prefix)
                except:
                    print('Your S3 bucket name is not corret or ' + args.target_list_name + '.csv cannot be found. The program will be terminated.')
                    exit()
    else:
        if not os.path.exists(args.target_list_name + '.csv'):
            print(args.target_list_name + '.csv cannot be found. The program will be terminated.')
            exit()

    main(args, obj)