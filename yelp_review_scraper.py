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
parser.add_argument('--wait_time_for_new_index', default=10, type=int)
parser.add_argument('--wait_time_for_establishment', default=10, type=int)
parser.add_argument('--wait_time_for_next_page_lb', default=10, type=int)
parser.add_argument('--wait_time_for_next_page_ub', default=15, type=int)
parser.add_argument('--index_specified_mode', default=0, type=int)
parser.add_argument('--page_specific_mode', default=0, type=int)
parser.add_argument('--index_for_ps_mode', default=-1, type=int)
parser.add_argument('--part_for_ps_mode', default=0, type=int)

# Log Options
parser.add_argument('--verbose', default=True, type=bool)
parser.add_argument('--save_log', default=False, type=bool)

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
    url = "https://www.yelp.com/biz/" + res['yelp_id']
    driver.get(url)
    time.sleep(args.wait_time_for_new_index)

    error_404 = len(driver.find_elements(By.CLASS_NAME, 'page-status')) > 0
    if error_404:
        logger.error('This page has been removed.')
        invalid_object_list.append(index)
        raise

    error = []

    # Name
    res_name = ""
    name_element = driver.find_elements(By.XPATH, '//h1[@class="css-wbh247"]')
    if len(name_element) > 0:
        res_name = name_element[0].text
    else:
        error.append("Name")
        res_name = "NA"

    # Closed
    is_closed = len(driver.find_elements(By.XPATH, '//*[contains(text(), \'Yelpers report this location has closed.\')]')) > 0
    if is_closed:
        if res_name != "":
            logger.info('[' + res_name + '] This location has closed.')
        else:
            logger.info('This location has closed.')

    # Ratings
    rating_element = driver.find_elements(By.XPATH, '//yelp-react-root/div[1]/div[3]/div[1]/div[1]/div/div/div[2]/div[1]/span/div')
    if len(rating_element) > 0:
        ratings = rating_element[0].get_attribute('aria-label')
        ratings = float(ratings[:ratings.find(" ")])
    else:
        error.append("Ratings")
        ratings = "NA"

    # Number of Total Reviews
    num_reviews_element = driver.find_elements(By.XPATH,
                                               '//yelp-react-root/div[1]/div[3]/div[1]/div[1]/div/div/div[2]/div[2]/span')
    if len(num_reviews_element) > 0:
        num_reviews = int(num_reviews_element[0].text[:num_reviews_element[0].text.find(" ")])
    else:
        error.append("Number of Total Reviews")
        num_reviews = "NA"

    # Claimed
    claimed_element = driver.find_elements(By.XPATH,
                                           '//yelp-react-root/div[1]/div[3]/div[1]/div[1]/div/div/span[1]/span/div/span')
    if len(claimed_element) > 0:
        claimed = claimed_element[0].text
    else:
        error.append("Claimed")
        claimed = "NA"

    # Price Range
    pricerange_element = driver.find_elements(By.XPATH, '/yelp-react-root/div[1]/div[3]/div[1]/div[1]/div/div/span[2]/span')
    if len(pricerange_element) > 0:
        pricerange = pricerange_element[0].text
    else:
        error.append("Price Range")
        priceranges = "NA"

    # Category list
    category_elements = driver.find_elements(By.XPATH, 'yelp-react-root/div[1]/div[3]/div[1]/div[1]/div/div/span[3]/span/a')
    if len(category_elements) > 0:
        category_list = ''
        first = True
        for element in category_elements:
            category = element.text
            if first:
                category_list = category
                first = False
            else:
                category_list = category_list + ", " + category
    else:
        error.append("Category List")
        category_lists = "NA"

    # Number of Photos Posted in Reviews
    photo_num_element = driver.find_elements(By.XPATH, '//a[@class="css-1enow5j"]/span')
    if len(photo_num_element) > 0:
        if photo_num_element[0].text == 'Add photo or video':
            photo_num = 0
        else:
            photo_num = int(photo_num_element[0].text.split(" ")[1])
    else:
        error.append("Number of Photos Posted in Reviews")
        photo_num = "NA"

    ############# Phone Number #############
    phone_icon_element = driver.find_elements(By.XPATH,
                                              '//span[@class="icon--24-phone-v2 icon__09f24__zr17A css-147xtl9"]')
    if len(phone_icon_element) == 0:
        phone_icon_element = driver.find_elements(By.XPATH,
                                                  '//span[@class="icon--24-phone-v2 icon__373c0__viOUw css-nyitw0"]')
    if len(phone_icon_element) == 0:
        error.append("Phone Number")
        phone_numbers = "NA"
    else:
        phone_number = phone_icon_element[0].find_elements(By.XPATH,
                                                           './../preceding-sibling::div/p[@class=" css-1h7ysrc"]')
        if len(phone_number) == 0:
            phone_number = phone_icon_element[0].find_elements(By.XPATH,
                                                               './../preceding-sibling::div/p[@class=" css-oe5jd3"]')
        phone_numbers = phone_number[0].text

    ############# Address #############
    direction_icon_element = driver.find_elements(By.XPATH,
                                                  '//span[@class="icon--24-directions-v2 icon__09f24__zr17A css-nyitw0"]')
    if len(direction_icon_element) == 0:
        direction_icon_element = driver.find_elements(By.XPATH,
                                                      '//span[@class="icon--24-directions-v2 icon__373c0__viOUw css-nyitw0"]')
    if len(direction_icon_element) == 0:
        error.append("Address")
        addresses = "NA"
    else:
        address = direction_icon_element[0].find_elements(By.XPATH,
                                                          './../../preceding-sibling::div/p[@class=" css-v2vuco"]')
        if len(address) == 0:
            address = direction_icon_element[0].find_elements(By.XPATH,
                                                              './../../preceding-sibling::div/p[@class=" css-1ccncw"]')
        if len(address) == 0:
            error.append("Address")
            addresses = "NA"
        else:
            addresses = address[0].text

    ############# Amenities #############
    possible_buttons = driver.find_elements(By.XPATH, '//button[@class=" css-zbyz55"]')

    # Check elements are really more attributes button
    for button in possible_buttons:
        button_name = button.find_elements(By.XPATH, './span/p')
        if len(button_name) > 0:
            if button_name[0].text.find("More Attributes") != -1:
                button.click()
                break
        else:
            continue

    amenities_elements = driver.find_elements(By.XPATH,
                                              '//div[@class=" arrange__373c0__3yvT_ gutter-2__373c0__1fwxZ layout-wrap__373c0__1j3yL layout-2-units__373c0__25Mue border-color--default__373c0__2s5dW"]/div')
    if len(amenities_elements) == 0:
        amenities_elements = driver.find_elements(By.XPATH,
                                                  '//div[@class=" arrange__09f24__LDfbs gutter-2__09f24__CCmUo layout-wrap__09f24__GEBlv layout-2-units__09f24__PsGVW border-color--default__09f24__NPAKY"]/div')
    if len(amenities_elements) == 0:
        error.append("Amenities")
        amenities = "NA"
    else:
        amenities_list = []
        class_names = [[' css-1h7ysrc', ' css-1ccncw'], [' css-oe5jd3', ' css-v2vuco']]
        amenity_desc = ''
        for amenities_element in amenities_elements:
            for name in class_names[0]:
                info = amenities_element.find_elements(By.XPATH, './/span[@class="' + name + '"]')
                if len(info) > 0:
                    amenity_desc = info[0].text
                    amenities_list.append(amenity_desc)
                    break

        if len(amenity_desc) == 0:
            for amenities_element in amenities_elements:
                for name in class_names[1]:
                    info = amenities_element.find_elements(By.XPATH, './/span[@class="' + name + '"]')
                    if len(info) > 0:
                        amenity_desc = info[0].text
                        amenities_list.append(amenity_desc)
                        break
        amenities = ", ".join(amenities_list)

    ############# Hours #############
    table_elements = driver.find_elements(By.XPATH,
                                          '//table[@class=" hours-table__373c0__2YHlD table__373c0__1FIZ8 table--simple__373c0__3QsR_"]/tbody/tr[@class=" table-row__373c0__1F6B0"]')
    if len(table_elements) == 0:
        table_elements = driver.find_elements(By.XPATH,
                                              '//table[@class=" hours-table__09f24__KR8wh table__09f24__J2OBP table--simple__09f24__vy16f"]/tbody/tr[@class=" table-row__09f24__YAU9e"]')
    if len(table_elements) == 0:
        error.append("Operating Hours")
        day_and_operating_times = "NA"
    else:
        day_and_operating_times = ''
        for tr in table_elements:
            day = tr.find_elements(By.XPATH, './th/p')[0].text
            if len(day) == 0:
                continue
            operating_times = []
            operating_times_element = tr.find_elements(By.XPATH, './td/ul/li')
            for element in operating_times_element:
                operating_time = element.find_element(By.XPATH, './p').text
                operating_times.append(operating_time)

            if len(day_and_operating_times) == 0:
                if len(operating_times) > 1:
                    day_and_operating_times = day + ": " + ", ".join(operating_times)
                else:
                    day_and_operating_times = day + ": " + operating_times[0]
            else:
                if len(operating_times) > 1:
                    day_and_operating_times = day_and_operating_times + " | " + day + ": " + ", ".join(operating_times)
                else:
                    day_and_operating_times = day_and_operating_times + " | " + day + ": " + operating_times[0]

    if len(error) == 0:
        logger.info('[' + res_name + ']: Done. All information has been successfully collected.')
    else:
        logger.info('[' + res_name + ']: Done. But some information was failed to be collected:')
        logger.info(", ".join(error))

    this_res_info = [res['yelp_id'], name, is_closed, claimed, ratings, num_reviews, priceranges, category_lists,
                     photo_num, phone_numbers, addresses, day_and_operating_times, amenities]
    restaurants[index] = this_res_info

def profile_scraper(driver, index, reviewer):
    logger.info('Current working index: ' + str(index) + '. User ID is ' + reviewer['user_id'] + '.')

    url = 'https://www.yelp.com/user_details?userid=' + reviewer['user_id']
    driver.get(url)
    time.sleep(args.wait_time_for_new_index)

    error_404 = len(driver.find_elements(By.XPATH, '//div[@class="arrange_unit arrange_unit--fill"]/p')) > 0
    if error_404:
        logger.error('This user has been removed.')
        invalid_object_list.append(index)
        raise

    profile_photo_urls = []

    photo_info = "yelp.www.init.user_details.initPhotoSlideshow(\".js-photo-slideshow-user-details\", "
    photo_slide_script = ""
    script_element = driver.find_elements(By.XPATH, '//*[contains(text(), \'yelp.www.init.user_details.initPhotoSlideshow\')]')
    if len(script_element) > 0:
        photo_slide_script = script_element[0].get_attribute('innerHTML')

    # No Photos or Only One Photo
    if photo_slide_script == "":
        photo_src = driver.find_elements(By.CLASS_NAME, 'photo-box-img')[0].get_attribute('src')
        if photo_src.find('user_large_square.png') == -1:
            profile_photo_urls.append(photo_src)
    else:
        start_index = photo_slide_script.find(photo_info)
        end_index = photo_slide_script.find(")", start_index)
        photo_list = json.loads(photo_slide_script[start_index + len(photo_info):end_index])

        for elm in photo_list:
            profile_photo_urls.append(elm['source_url'])
    profile_photo_urls = ', '.join(profile_photo_urls)

    user_profile_info = driver.find_elements(By.XPATH, '//div[@class="user-profile_info arrange_unit"]')[0]
    name = ""
    nickname = ""
    name_element = user_profile_info.find_elements(By.XPATH, './h1')
    if len(name_element) > 0:
        full_name = name_element[0].text
        if full_name.find("\"") != -1:
            name = full_name[:full_name.find("\"")] + full_name[full_name.rfind("\"") + 2:]
            nickname = full_name[full_name.find("\"") + 1:full_name.rfind("\"")]
        else:
            name = full_name

    user_passport_stats = user_profile_info.find_elements(By.XPATH, './/div[@class="clearfix"]/ul')[0]
    friend_count_element = user_passport_stats.find_elements(By.XPATH, '//li[@class="friend-count"]')[0]
    review_count_element = user_passport_stats.find_elements(By.XPATH, '//li[@class="review-count"]')[0]
    photo_count_element = user_passport_stats.find_elements(By.XPATH, '//li[@class="photo-count"]')[0]

    friends = int(friend_count_element.find_element(By.XPATH, './strong').text)
    reviews = int(review_count_element.find_element(By.XPATH, './strong').text)
    photos = int(photo_count_element.find_element(By.XPATH, './strong').text)

    elites = []
    badges = user_profile_info.find_elements(By.XPATH, './/div[@class="clearfix u-space-b1"]/a[1]/span')
    if len(badges) > 0:
        for badge in badges:
            if badge.get_attribute("class").find('show-tooltip') != -1:
                continue
            year_text = badge.text
            if year_text.find('Elite') != -1:
                year = year_text.split(' ')[1]
            else:
                year = "20" + str(int(year_text[1:]))
            elites.append(year)
    elites = ', '.join(elites)

    tagline = ""
    tagline_element = user_profile_info.find_elements(By.XPATH, './p[@class="user-tagline"]')
    if len(tagline_element) > 0:
        tagline = tagline_element[0].text[1:-1]

    about_elements = driver.find_elements(By.XPATH, '//div[@class="user-details-overview_sidebar"]/div')

    # Rating Distribution
    star_5 = 0
    star_4 = 0
    star_3 = 0
    star_2 = 0
    star_1 = 0

    # Review Votes
    useful = 0
    funny = 0
    cool = 0

    # Stats
    tips = 0
    review_updates = 0
    bookmarks = 0
    firsts = 0
    followers = 0
    lists = 0

    # Compliments
    thank_you = 0  # compliment
    cute_pic = 0  # heart
    good_writer = 0  # pencil
    hot_stuff = 0  # flame
    just_a_note = 0  # file
    like_your_profile = 0  # profile
    write_more = 0  # write_more
    you_are_cool = 0  # cool
    great_photos = 0  # camera
    great_lists = 0  # list
    you_are_funny = 0  # funny

    # etc_info
    location = ""
    yelping_since = ""
    things_i_love = ""

    find_me_in = ""
    my_hometown = ""
    my_blog_or_website = ""
    when_im_not_yelping = ""
    why_ysrmr = ""
    my_second_fw = ""
    last_great_book = ""
    my_first_concert = ""
    my_favorite_movie = ""
    my_last_meal_on_earth = ""
    dont_tell_anyone_else_but = ""
    most_recent_discovery = ""
    current_crush = ""

    for ysection in about_elements:
        h4 = ysection.find_elements(By.XPATH, './h4')
        if len(h4) > 0:
            section_name = h4[0].text
            # Rating Distribution
            if section_name.find('Rating Distribution') != -1:
                row_elements = ysection.find_elements(By.XPATH, './table/tbody/tr')
                for row_element in row_elements:
                    rating_num = int(row_element.find_elements(By.XPATH, './td/table/tbody/tr/td[2]')[0].text)
                    if row_element.get_attribute('class').find('1') != -1:
                        star_5 = rating_num
                    elif row_element.get_attribute('class').find('2') != -1:
                        star_4 = rating_num
                    elif row_element.get_attribute('class').find('3') != -1:
                        star_3 = rating_num
                    elif row_element.get_attribute('class').find('4') != -1:
                        star_2 = rating_num
                    elif row_element.get_attribute('class').find('5') != -1:
                        star_1 = rating_num

            # Review Votes
            elif section_name.find('Review Votes') != -1:
                votes_elements = ysection.find_elements(By.XPATH, './ul/li')
                for votes_element in votes_elements:
                    votes_text = votes_element.text
                    votes_num = int(votes_element.find_elements(By.XPATH, './strong')[0].text)
                    if votes_text.find('Useful') != -1:
                        useful = votes_num
                    elif votes_text.find('Funny') != -1:
                        funny = votes_num
                    elif votes_text.find('Cool') != -1:
                        cool = votes_num

            # Stats
            elif section_name.find('Stats') != -1:
                stats_elements = ysection.find_elements(By.XPATH, './ul/li')
                for stats_element in stats_elements:
                    stats_text = stats_element.text
                    stats_num = int(stats_element.find_elements(By.XPATH, './strong')[0].text)
                    if stats_text.find('Tips') != -1:
                        tips = stats_num
                    elif stats_text.find('Review Updates') != -1:
                        review_updates = stats_num
                    elif stats_text.find('Bookmarks') != -1:
                        bookmarks = stats_num
                    elif stats_text.find('Firsts') != -1:
                        firsts = stats_num
                    elif stats_text.find('Followers') != -1:
                        followers = stats_num
                    elif stats_text.find('Lists') != -1:
                        lists = stats_num

            # Compliments
            elif section_name.find('Compliments') != -1:
                compliment_elements = ysection.find_elements(By.XPATH, './ul/li')
                if len(compliment_elements) > 0:
                    for compliment_element in compliment_elements:
                        compliment_type = compliment_element.find_elements(By.XPATH, './div[1]/span')[0].get_attribute(
                            'class')
                        compliment_num = int(compliment_element.find_elements(By.XPATH, './div[2]/small')[0].text)
                        if compliment_type.find('icon--18-compliment') != -1:
                            thank_you = compliment_num
                        elif compliment_type.find('icon--18-heart') != -1:
                            cute_pic = compliment_num
                        elif compliment_type.find('icon--18-pencil') != - 1:
                            good_writer = compliment_num
                        elif compliment_type.find('icon--18-flame') != -1:
                            hot_stuff = compliment_num
                        elif compliment_type.find('icon--18-file') != -1:
                            just_a_note = compliment_num
                        elif compliment_type.find('icon--18-profile') != -1:
                            like_your_profile = compliment_num
                        elif compliment_type.find('icon--18-write-more') != -1:
                            write_more = compliment_num
                        elif compliment_type.find('icon--18-cool') != -1:
                            you_are_cool = compliment_num
                        elif compliment_type.find('icon--18-camera') != -1:
                            great_photos = compliment_num
                        elif compliment_type.find('icon--18-list') != -1:
                            great_lists = compliment_num
                        elif compliment_type.find('icon--18-funny') != -1:
                            you_are_funny = compliment_num

        # Etc..
        ul_element = ysection.find_elements(By.XPATH, './ul')
        if len(ul_element) > 0:
            if ul_element[0].get_attribute('class') == 'ylist':
                extra_elements = ul_element[0].find_elements(By.XPATH, './li')
                if len(extra_elements) > 0:
                    for extra_element in extra_elements:
                        title = extra_element.find_elements(By.XPATH, './h4')[0].text
                        content = extra_element.find_elements(By.XPATH, './p')[0].text
                        if title.find("Location") != -1:
                            location = content
                        elif title.find("Yelping Since") != -1:
                            yelping_since = content
                        elif title.find("Things I Love") != -1:
                            things_i_love = content
                        elif title.find("Find Me In") != -1:
                            find_me_in = content
                        elif title.find("My Hometown") != -1:
                            my_hometown = content
                        elif title.find("My Blog Or Website") != -1:
                            my_blog_or_website = content
                        elif title.find("When I’m Not Yelping...") != -1:
                            when_im_not_yelping = content
                        elif title.find("Why You Should Read My Reviews") != -1:
                            why_ysrmr = content
                        elif title.find("My Second Favorite Website") != -1:
                            my_second_fw = content
                        elif title.find("The Last Great Book I Read") != -1:
                            last_great_book = content
                        elif title.find("My First Concert") != -1:
                            my_first_concert = content
                        elif title.find("My Favorite Movie") != -1:
                            my_favorite_movie = content
                        elif title.find("My Last Meal On Earth") != -1:
                            my_last_meal_on_earth = content
                        elif title.find("Don’t Tell Anyone Else But...") != -1:
                            dont_tell_anyone_else_but = content
                        elif title.find("Most Recent Discovery") != -1:
                            most_recent_discovery = content
                        elif title.find("Current Crush") != -1:
                            current_crush = content

    this_profile = [reviewer['user_id'], name, nickname, profile_photo_urls, friends, reviews, photos, elites, tagline,
                    star_5, star_4, star_3, star_2, star_1, useful, funny, cool, tips, review_updates, bookmarks, firsts,
                    followers, lists, thank_you, cute_pic, good_writer, hot_stuff, just_a_note, like_your_profile,
                    write_more, you_are_cool, great_photos, great_lists, you_are_funny, location, yelping_since,
                    things_i_love, find_me_in, my_hometown, my_blog_or_website, when_im_not_yelping, why_ysrmr,
                    my_second_fw, last_great_book, my_first_concert, my_favorite_movie, my_last_meal_on_earth,
                    dont_tell_anyone_else_but, most_recent_discovery, current_crush]
    profiles[index] = this_profile

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
            logger.info('Current Index: {}, Page: 1 / {}, Acutal Page: Home'.format(str(index), str(loaded_page_num)))
        else:
            current_page = list_of_page.pop()
            logger.info(
                'Current Index: {}, Page: {} / {}, Acutal Page: {}'.format(str(index), str(page), str(loaded_page_num),
                                                                           current_page))
            driver.get(yelp_url + current_page)
            random_sleep_within_page = random.randint(args.wait_time_for_next_page_lb, args.wait_time_for_next_page_ub)
            while random_sleep_within_page == previous_sleep_time_within_page:
                random_sleep_within_page = random.randint(args.wait_time_for_next_page_lb,
                                                          args.wait_time_for_next_page_ub)
            time.sleep(random_sleep_within_page)
            previous_sleep_time_within_page = random_sleep_within_page


            navigation_elements = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, './/div[@aria-label="Pagination navigation"]')))
            current_page_num = int(navigation_elements[0].find_elements(By.XPATH, './div[2]/span')[0].text.split('of')[0])
            this_total_page_num = int(
                navigation_elements[0].find_elements(By.XPATH, './div[2]/span')[0].text.split('of')[1]) 
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
                                                                      './/span[contains(text(), "check-ins")]')
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

    class_names, xpaths = utils.load_class_name_and_xpath('keys_for_scraping.ini')

    if platform.system() == 'Windows':
        driver = webdriver.Chrome(options=chrome_options)
    else:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
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
        if not 'user_id' in yelp_target_df.columns:
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
        end_idx = int(args.part_for_ps_mode * unit) if args.part_for_ps_mode != 10 else len(total_list_of_page)
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
    while(True):
        global success_num, fail_num
        if len(index_set) == 0:
            break

        try:
            for index, object in yelp_target_df.iterrows():
                if args.collected_object == 'profile':
                    profile_scraper(driver, index, object)
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
        logger.info('Please check class names and xpaths in keys_for_scraping.ini file. They may be not valid.')

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
        if not os.path.exists('index_set.txt'):
            print('index_set.txt cannot be found. The program will be terminated.')
            exit()

        if len(utils.load_specific_mode_filet('index_set.txt')) == 0:
            print('index_set.txt is empty or invalid. The program will be terminated.')
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

    if args.wait_time_for_establishment < 0:
        parser_error = True
        parser.error('Wait time for establishment cannot be negative.')

    if args.wait_time_for_next_page_lb < 0 or args.wait_time_for_next_page_ub < 0:
        parser_error = True
        parser.error('Wait time for next page cannot be negative.')

    if parser_error:
        print('Some arguments you entered are not valid. The program will be terminated.')
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

    if not os.path.exists('keys_for_scraping.ini'):
        print('keys_for_scraping.ini cannot be found. The program will be terminated.')
        exit()

    main(args, obj)