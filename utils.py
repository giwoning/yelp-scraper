import configparser

import pandas as pd

def load_class_name_and_xpath(_path):
    names = {}
    xpaths = {}

    parser = configparser.ConfigParser()
    parser.read(_path)

    for option in parser.options('Class Names'):
        names[option] = parser.get('Class Names', option)[1:-1]

    for option in parser.options('XPaths'):
        xpaths[option] = parser.get('XPaths', option)[1:-1]

    return names, xpaths

def load_aws_keys(_path):
    aws_info = {}

    parser = configparser.ConfigParser()
    parser.read(_path)

    for option in parser.options('AWS Keys'):
        aws_info[option] = parser.get('AWS Keys', option)[1:-1]

    return aws_info['aws_access_key'], aws_info['aws_secret_key'], aws_info['aws_region'], aws_info['aws_bucket_name']

def load_index_set(_path):
    iset = set()
    with open(_path, 'r') as f:
        for line in f:
            line = line.strip().split(',')
            if '' in line:
                line.remove('')
            iset.update([int(index) for index in line])
    return iset

def check_index_list(ilist, max_index):
    pass_ = True
    for index in ilist:
        if index < 0 or index > max_index:
            pass_ = False
    return pass_

def set_to_df(_set, mode):
    if mode == 'profile':
        profile_info = ['userid', 'name', 'nickname', 'profile_photo_urls', 'friends', 'reviews', 'photos', 'elites', 'tagline',
                        'star_5', 'star_4', 'star_3', 'star_2', 'star_1', 'useful', 'funny', 'cool', 'tips',
                        'review_updates', 'bookmarks', 'firsts', 'followers', 'lists', 'thank_you', 'cute_pic',
                        'good_writer', 'hot_stuff', 'just_a_note', 'like_your_profile', 'write_more', 'you_are_cool',
                        'great_photos', 'great_lists', 'you_are_funny', 'location', 'yelping_since', 'things_i_love',
                        'find_me_in', 'my_hometown', 'my_blog_or_website', 'when_im_not_yelping', 'why_ysrmr',
                        'my_second_fw', 'last_great_book', 'my_first_concert', 'my_favorite_movie',
                        'my_last_meal_on_earth', 'dont_tell_anyone_else_but', 'most_recent_discovery', 'current_crush']
        all_profiles = pd.DataFrame(columns=profile_info)

        for profiles in _set.values():
            userid = profiles[0]
            name = profiles[1]
            nickname = profiles[2]
            profile_photo_urls = profiles[3]
            friends = profiles[4]
            reviews = profiles[5]
            photos = profiles[6]
            elites = profiles[7]
            tagline = profiles[8]
            star_5 = profiles[9]
            star_4 = profiles[10]
            star_3 = profiles[11]
            star_2 = profiles[12]
            star_1 = profiles[13]
            useful = profiles[14]
            funny = profiles[15]
            cool = profiles[16]
            tips = profiles[17]
            review_updates = profiles[18]
            bookmarks = profiles[19]
            firsts = profiles[20]
            followers = profiles[21]
            lists = profiles[22]
            thank_you = profiles[23]
            cute_pic = profiles[24]
            good_writer = profiles[25]
            hot_stuff = profiles[26]
            just_a_note = profiles[27]
            like_your_profile = profiles[28]
            write_more = profiles[29]
            you_are_cool = profiles[30]
            great_photos = profiles[31]
            great_lists = profiles[32]
            you_are_funny = profiles[33]
            location = profiles[34]
            yelping_since = profiles[35]
            things_i_love = profiles[36]
            find_me_in = profiles[37]
            my_hometown = profiles[38]
            my_blog_or_website = profiles[39]
            when_im_not_yelping = profiles[40]
            why_ysrmr = profiles[41]
            my_second_fw = profiles[42]
            last_great_book = profiles[43]
            my_first_concert = profiles[44]
            my_favorite_movie = profiles[45]
            my_last_meal_on_earth = profiles[46]
            dont_tell_anyone_else_but = profiles[47]
            most_recent_discovery = profiles[48]
            current_crush = profiles[49]

            this_profile = pd.DataFrame.from_records([{'userid' : userid,
                                                       'name' : name,
                                                      'nickname' : nickname,
                                                      'profile_photo_urls': profile_photo_urls,
                                                      'friends' : friends,
                                                      'reviews' : reviews,
                                                      'photos' : photos,
                                                       'elites': elites,
                                                       'tagline': tagline,
                                                      'star_5' : star_5,
                                                      'star_4' : star_4,
                                                      'star_3' : star_3,
                                                      'star_2' : star_2,
                                                      'star_1' : star_1,
                                                      'useful' : useful,
                                                      'funny' : funny,
                                                     'cool': cool,
                                                     'tips': tips,
                                                     'review_updates': review_updates,
                                                     'bookmarks': bookmarks,
                                                     'firsts': firsts,
                                                       'followers': followers,
                                                       'lists': lists,
                                                       'thank_you': thank_you,
                                                       'cute_pic': cute_pic,
                                                       'good_writer': good_writer,
                                                       'hot_stuff': hot_stuff,
                                                       'just_a_note': just_a_note,
                                                       'like_your_profile': like_your_profile,
                                                       'write_more': write_more,
                                                       'you_are_cool': you_are_cool,
                                                       'great_photos': great_photos,
                                                       'great_lists': great_lists,
                                                       'you_are_funny': you_are_funny,
                                                        'location': location,
                                                       'yelping_since': yelping_since,
                                                       'things_i_love': things_i_love,
                                                       'find_me_in': find_me_in,
                                                       'my_hometown': my_hometown,
                                                       'my_blog_or_website': my_blog_or_website,
                                                       'when_im_not_yelping': when_im_not_yelping,
                                                       'why_ysrmr': why_ysrmr,
                                                       'my_second_fw': my_second_fw,
                                                       'last_great_book': last_great_book,
                                                       'my_first_concert': my_first_concert,
                                                       'my_favorite_movie': my_favorite_movie,
                                                       'my_last_meal_on_earth': my_last_meal_on_earth,
                                                        'dont_tell_anyone_else_but': dont_tell_anyone_else_but,
                                                       'most_recent_discovery': most_recent_discovery,
                                                       'current_crush': current_crush}])
            all_profiles = pd.concat([all_profiles, this_profile])

        return all_profiles

    elif mode == 'review':
        review_info = ['yelpid', 'name', 'user_name', 'user_id', 'user_elite', 'user_first_review',
                       'user_loc', 'user_friend_num', 'user_review_num', 'user_photos_num',
                       'rating', 'date', 'updated', 'posted_photo_num',
                       'check_ins_num', 'comment', 'helpful', 'thanks', 'love_this',
                       'oh_no', 'owner_comment_date', 'owner_comment', 'previous_ratings',
                       'previous_dates', 'previous_comments', 'previous_helpfuls',
                       'previous_thanks', 'previous_love_this', 'previous_oh_no']
        all_reviews = pd.DataFrame(columns=review_info)

        for reviews in _set.values():
            yelp_id = reviews[0]
            yelp_name = reviews[1]
            user_name = reviews[2]
            user_id = reviews[3]
            user_elite = reviews[4]
            user_first_reivew = reviews[5]
            user_loc = reviews[6]
            user_friend_num = reviews[7]
            user_review_num = reviews[8]
            user_photos_num = reviews[9]
            rating = reviews[10]
            date = reviews[11]
            user_review_updated = reviews[12]
            user_num_posted_photo = reviews[13]
            user_num_check_ins = reviews[14]
            comment = reviews[15]
            helpful = reviews[16]
            thanks = reviews[17]
            love_this = reviews[18]
            oh_no = reviews[19]
            owner_comment_date = reviews[20]
            owner_comment = reviews[21]
            previous_ratings = reviews[22]
            previous_dates = reviews[23]
            previous_comments = reviews[24]
            previous_helpfuls = reviews[25]
            previous_thankss = reviews[26]
            previous_love_thiss = reviews[27]
            previous_oh_nos = reviews[28]

            this_reviews = pd.DataFrame({'yelpid': yelp_id, 'name': yelp_name,
                                         'user_name': user_name, 'user_id': user_id,
                                         'user_elite': user_elite, 'user_first_review': user_first_reivew,
                                         'user_loc': user_loc, 'user_friend_num': user_friend_num,
                                         'user_review_num': user_review_num,
                                         'user_photos_num': user_photos_num,
                                         'rating': rating, 'date': date, 'updated': user_review_updated,
                                         'posted_photo_num': user_num_posted_photo,
                                         'check_ins_num': user_num_check_ins,
                                         'comment': comment, 'helpful': helpful, 'thanks': thanks,
                                         'love_this': love_this, 'oh_no': oh_no,
                                         'owner_comment_date': owner_comment_date,
                                         'owner_comment':owner_comment,
                                         'previous_ratings': previous_ratings,
                                         'previous_dates': previous_dates,
                                         'previous_comments': previous_comments,
                                         'previous_helpfuls': previous_helpfuls,
                                         'previous_thanks': previous_thankss,
                                         'previous_love_this': previous_love_thiss,
                                         'previous_oh_no': previous_oh_nos})

            all_reviews = pd.concat([all_reviews, this_reviews])

        return all_reviews

    else:
        res_info = ['yelpid', 'name', 'closed', 'verified', 'rating', 'review', 'princerange', 'categorylist', 'photos',
                    'phone', 'address', 'openingtimes', 'morebusinessinfo']
        all_res_info = pd.DataFrame(columns=res_info)

        for res in _set.values():
            yelpid = res[0]
            name = res[1]
            closed = res[1]
            claimed = res[2]
            rating = res[3]
            review = res[4]
            pricerange = res[5]
            categorylist = res[6]
            photos = res[7]
            phone = res[8]
            address = res[9]
            openingtimes = res[10]
            morebusinessinfo = res[11]

            this_res = pd.DataFrame({'yelpid': yelpid,
                                     'name': name,
                                     'closed': closed,
                                     'verified': claimed,
                                     'rating': rating,
                                     'review': review,
                                     'pricerange': pricerange,
                                     'categorylist': categorylist,
                                     'photos': photos,
                                     'phone': phone,
                                     'address': address,
                                     'openingtimes': openingtimes,
                                     'morebusinessinfo': morebusinessinfo})
            all_res_info = pd.concat([all_res_info, this_res])

        return all_res_info