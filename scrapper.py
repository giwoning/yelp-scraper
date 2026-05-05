import argparse
import time
import logging
import os
import re
from timeit import default_timer as timer
import glob
from enum import Enum, auto
from datetime import datetime

import pandas as pd
import numpy as np
from bs4 import BeautifulSoup
from model.review import Review, Restaurant, YelpHTML
import utils
from urllib.parse import urlencode

MAX_CONCURRENCY_NUM = 150

parser = argparse.ArgumentParser()

# Scraper Options
parser.add_argument('-minIdx', default=-1, type=int)
parser.add_argument('-maxIdx', default=-1, type=int)
parser.add_argument('-cid', default=-1, type=int)
parser.add_argument('-yelpid', default='', type=str)
parser.add_argument('-pageNum', default=1, type=int)
parser.add_argument('-indexListFile', default='', type=str)
parser.add_argument('-ignorePreviousReview', default=0, type=int)
parser.add_argument('-outputFolderName', default='output', type=str)
parser.add_argument('-searchFile', default='', type=str)
parser.add_argument('-errorCorrection', default=0, type=int)

# Log Options
parser.add_argument('-verbose', default=1, type=int)

# Dataset Option
parser.add_argument('-targetList', default='target_list', type=str)

# API Option
parser.add_argument('-APIKey', default='', type=str)
parser.add_argument('-retrialNum', default=10, type=int)

args = parser.parse_args()

# Logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

formatter = logging.Formatter('[%(asctime)s][%(levelname)s] %(message)s', datefmt='%H:%M:%S')

streamHandler = logging.StreamHandler()
streamHandler.setFormatter(formatter)
logger.addHandler(streamHandler)

class Agent(Enum):
    SINGLE = auto()
    CONCURRENCY = auto()

    @property
    def label(self):
        displayNames = {
            Agent.SINGLE: 'Single',
            Agent.CONCURRENCY: 'Concurrency'
        }
        return displayNames.get(self, self.name)

class Mode(Enum):
    SELECTION = auto()
    ONE_URL = auto() # Single Agent에 대해서만 유효
    INDEX_RANGE = auto()
    OUTPUT_AUTO = auto()
    UNDEFINED = auto()
    SEARCH = auto()
    
    @property
    def label(self):
        displayNames = {
            Mode.SELECTION: 'Selection',
            Mode.ONE_URL: 'One URL',
            Mode.INDEX_RANGE: 'Index Range',
            Mode.OUTPUT_AUTO: 'Output Auto',
            Mode.SEARCH: 'Search',
            Mode.UNDEFINED: 'Undefined'
        }
        return displayNames.get(self, self.name)

# Return 
# 1: Successfully scrapped the page
# 0: Falied to scrape
# -1: No review
# (Search Mode) -2: 0 serach results
# (Search Mode) -3: 0 matched results
def doScraping(soup: BeautifulSoup, res: Restaurant, pageNum:int, ignorePreviousReview:bool=False, searchReviewInfo:dict=None):
    reviewParentElement = soup.find('div', id='reviews')
    reviewElements = reviewParentElement.select('section > div:nth-of-type(2) > ul > li')
    ReviewCntElement = soup.find_all(lambda tag: tag.name == 'a' and tag.get_text() and "Hey there trendsetter! You could be the first review for" in tag.get_text())
    if len(ReviewCntElement) > 0:
        return -1
    else:
        if searchReviewInfo is not None:
            searchResultElement = soup.find_all(lambda tag: tag.name == 'span' and tag.get_text() and "0 reviews mentioning" in tag.get_text())
            if len(searchResultElement) > 0:
                return -2
        reviewCnt = 0
        if searchReviewInfo is not None:
            nonMatchCase = 0
        for reviewElement in reviewElements:
            if len(reviewElement) == 0:
                continue
            thisReview = Review()
            userInfoElement = reviewElement.find('div', class_='user-passport-info')
            # User ID
            thisUserID = userInfoElement.select_one('span > a')['href'].split('?')[1].replace('userid=', '')
            if searchReviewInfo is not None and searchReviewInfo['userid'] != thisUserID:
                nonMatchCase += 1
                reviewCnt += 1
                continue
            thisReview.setUserID(thisUserID)
            # User Name
            thisReview.setUserName(userInfoElement.select_one('span > a').text)
            # User Elite
            userEliteElement = userInfoElement.select('div[class*="elite-badge"]')
            thisReview.setElite(1 if len(userEliteElement) > 0 else 0)
            # User Short Address
            userShortAddressElement = userInfoElement.select_one('div[data-testid*="UserPassportInfoTextContainer"] > span')
            if userShortAddressElement is not None:
                thisReview.setShortAddress(userShortAddressElement.text)
            else:
                thisReview.setShortAddress(None)
            # First Review
            firstReviewElement = reviewElement.select_one('span:-soup-contains("First to Review")')
            thisReview.setFirstReview(1 if firstReviewElement is not None else 0)
            # User Passport Stats
            passportStatElements = reviewElement.select('div[class*="user-passport-stats"] > div')
            passportDict = {}
            if len(passportStatElements) > 0:
                for passportStatElement in passportStatElements:
                    statName = passportStatElement.get('aria-label')
                    statValue = int(passportStatElement.select_one('span:nth-of-type(2) > span').text)
                    passportDict[statName] = statValue
            thisReview.setPassport(passportDict)
            # User Recognition
            recognitionElement = reviewElement.select_one('a[href*="recognition="]')
            if recognitionElement is not None:
                thisReview.setRecognition(recognitionElement.text)
            # Rating
            ratingElement = reviewElement.select_one('div[aria-label*="star rating"]')
            thisReview.setRating(int(ratingElement.get('aria-label').split(' ')[0]))
            # Review Date
            dateElement = ratingElement.find_parent().find_parent().find_parent().find_next_sibling().select_one('span')
            thisReview.setReviewDate(dateElement.text)
            # Updated
            updatedElement = reviewElement.select_one('span:-soup-contains("Updated review")')
            thisReview.setUpdated(1 if updatedElement is not None else 0)
            # Number of photos
            postedPhotosNum = 0
            postedPhotosElement = reviewElement.select_one('a[href*="biz_photos/"]')
            if postedPhotosElement is not None:
                moreReadText = True if postedPhotosElement.text.find('See all photos') != -1 else False
                if not moreReadText:
                    postedPhotosNum = int(re.sub(r'[^0-9]', '', postedPhotosElement.text))
            thisReview.setPhotoNums(postedPhotosNum)
            # Comments
            commentElement = reviewElement.select('p[class*="comment"]')[0] # 최근 코멘트 선택
            thisReview.setReviewComment(commentElement.select_one('span').text)
            # Reactions
            reactionDict = {}
            reactionElements = reviewElement.select('div[aria-label*="reaction"][role="button"]')[:4] # 최근 코멘트의 반응만 선택
            for reactionElement in reactionElements:
                thisReactionInfo = reactionElement.get('aria-label')
                reactionType = thisReactionInfo.split('(')[0].strip()
                reactionNums = int(re.sub(r'[^0-9]', '', thisReactionInfo))
                reactionDict[reactionType] = reactionNums
            thisReview.setReactions(reactionDict)
            # Previous Review
            thisReview.setPreviousReview(0)
            # Owner Reply
            ownerRepliedElements = reviewElement.select_one('div[data-testid*="business-owner-passport"]')
            if ownerRepliedElements is not None:
                ownerReplyElements = ownerRepliedElements.find_parent().find_parent().find_next_sibling()
                ownerReplyDateElement = ownerReplyElements.select_one('div > p')
                ownerCommentElement = ownerReplyElements.select_one('p > span')
                thisReview.setOwnerReplyDate(ownerReplyDateElement.text)
                thisReview.setOwnerComment(ownerCommentElement.text)
            thisReview.setPageNum(pageNum)
            res.addReview(thisReview)
            reviewCnt += 1
            
            # Previous Reviews
            if not ignorePreviousReview:
                pvReviewElements = reviewElement.find_all('span', attrs={"data-font-weight":"semibold"}, string='Previous review')
                if len(pvReviewElements) > 0:
                    for pvReviewElement in pvReviewElements:
                        pvReview = Review(userName=thisReview.userName, userID=thisReview.userID, isElite=thisReview.isElite, shortAddress=thisReview.shortAddress, recognition=thisReview.recognition, passport=thisReview.passport)
                        pvReviewRatingElement = pvReviewElement.find_parent().find_parent().find_previous_sibling().select_one('div[aria-label*="star rating"]')
                        pvReviewDateElement = pvReviewElement.find_parent().find_previous_sibling()
                        pvReviewSecondBoxElement = pvReviewElement.find_parent().find_parent().find_parent().find_parent().find_parent().find_parent().find_next_sibling()
                        pvReviewCommentElement = pvReviewSecondBoxElement.select_one('p[class*="comment"] > span')
                        pvReactionElements = list(pvReviewCommentElement.find_parent().find_parent().next_siblings)[-1].select('div[aria-label*="reaction"]')[:4]
                        pvReview.setRating(int(re.sub(r'[^0-9]', '', pvReviewRatingElement.get('aria-label'))))
                        pvReview.setReviewDate(pvReviewDateElement.text)
                        pvReview.setReviewComment(pvReviewCommentElement.text)
                        pvReactionDict = {}
                        for pvReactionElement in pvReactionElements:
                            pvReactionInfo = pvReactionElement.get('aria-label')
                            pvReactionType = pvReactionInfo.split('(')[0].strip()
                            pvReactionNums = int(re.sub(r'[^0-9]', '', pvReactionInfo))
                            pvReactionDict[pvReactionType] = pvReactionNums
                        pvReview.setReactions(pvReactionDict)
                        pvReview.setPreviousReview(1)
                        pvReview.setPageNum(pageNum)
                        res.addReview(pvReview)
                        reviewCnt += 1
        if searchReviewInfo is not None:
            if reviewCnt > 0 and reviewCnt == nonMatchCase:
                return -3
        return (reviewCnt > 0)

def scrape(args, agent: Agent, mode: Mode, idxDict: dict, outputFolderName):
    logger.info(f'Current Mode: {mode.label}')
    # 전체 수집 대상 레스토랑 데이터 불러오기
    if mode == Mode.ONE_URL:
        logger.info(f'Yelp ID: {args.yelpid}, Page Number: {args.pageNum}')
        st = time.time()
        if args.pageNum > 0:
            url = f'https://yelp.com/biz/{args.yelpid}?start={(args.pageNum - 1) * 10}&sort_by=date_asc'
        else:
            url = f'https://yelp.com/biz/{args.yelpid}?sort_by=date_asc'
        thisHTML = YelpHTML(url, args.APIKey, args.retrialNum, args.ignorePreviousReview)
        thisSoup = thisHTML.getSoup()
        if type(thisSoup) == int:
            if thisSoup == 404:
                logger.error('Page Not Found (Error 404).')
            elif thisSoup == -1:
                logger.error('Maximum Retrial Number Reached (Error -1).')
            else:
                logger.error(f'Error Occured (Error Code: {thisSoup})')
            exit()
        thisRes = Restaurant(args.yelpid, '')
        doScraping(thisSoup, thisRes, args.pageNum, args.ignorePreviousReview)
        et = time.time()
        logger.info('===============================================')
        logger.info('Scrapping has been completed.')
        logger.info('===============================================')
        logger.info(f'Yelp ID: {args.yelpid}, Page: {args.pageNum}')
        logger.info(f'The number of collected reviews: {thisRes.getNumReviews()}')
        logger.info(f'The elapsed time: {utils.formatSec((et - st))}')
        logger.info('Saving the result...')
        outputDF = thisRes.toDataFrame()
        outputDF.to_csv(f'./{outputFolderName}/{args.yelpid}.csv', encoding='utf-8', index=False)
        logger.info('Done. Requested jobs has been finished.')

    else:
        ######################################
        ####### Part 1: List File Load #######
        ######################################
        thisPrefix = utils.setLoggerPrefix(args.cid, resInfo=None, pageInfo=None)
        elapsedTimeDict = {}
        totResDF = pd.read_csv(args.targetList + '.csv', encoding='utf-8')
        if args.verbose:
            logger.info(thisPrefix + f'The list file with size {len(totResDF):,} loaded.')
        totResDF['idx'] = [i for i in range(len(totResDF))]
        idxList = list(idxDict.keys())
        targetResDF = totResDF[totResDF['idx'].isin(idxList)]
        if args.verbose:
            logger.info(thisPrefix + f'Found the total {len(targetResDF):,} restaurants in the list file.')
            if mode == Mode.INDEX_RANGE:
                logger.info(f'Min Index: {sorted(idxList)[0]}')
                logger.info(f'Max Index: {sorted(idxList)[-1]}')
            else:
                logger.info(f'The total {len(idxList):,} target restaurants.')
        if mode == Mode.SEARCH:
            searchDF = pd.read_csv(args.searchFile, encoding='utf-8')
            searchDF = searchDF[searchDF['yelpid'].isin(targetResDF['yelpid'].to_list())]
            if args.verbose:
                logger.info(f'The selected reviews with size {len(searchDF)} loaded.')

        totDict = {}
        totDict['success'] = []
        totDict['fail'] = []
        skipCnt = 0

        invalidIdxDict = {}
        errorFileList = [file for file in os.listdir('./search_error')]
        emptyResultList = [file for file in os.listdir('./search_empty_result')]
        noResultList = [file for file in os.listdir('./search_no_result')]
        for file in errorFileList + emptyResultList + noResultList:
            thisIdx = int(file.split('.')[0].split('_')[0])
            thisPageIdx = int(file.split('.')[0].split('_')[1])
            if thisIdx not in invalidIdxDict:
                invalidIdxDict[thisIdx] = []
            invalidIdxDict[thisIdx].append(thisPageIdx)

        if args.errorCorrection == 1:
            finalErrorFileList = [file for file in os.listdir('./final_search_error')]
            finalEmptyResultList = [file for file in os.listdir('./final_empty_result')]
            finalNoResultList = [file for file in os.listdir('./final_no_result')]
            for file in finalErrorFileList + finalEmptyResultList + finalNoResultList:
                thisIdx = int(file.split('.')[0].split('_')[0])
                thisPageIdx = int(file.split('.')[0].split('_')[1])
                if thisIdx in invalidIdxDict:
                    if thisPageIdx in invalidIdxDict[thisIdx]:
                        invalidIdxDict[thisIdx].remove(thisPageIdx)
                
                    if len(invalidIdxDict[thisIdx]) == 0:
                        del invalidIdxDict[thisIdx]

        invalidReactionIdx = []
        emptyResultIdx = []
        resultFileList = [file for file in os.listdir('./output') if int(file.split('.')[0]) in list(targetResDF.index)]
        if not args.errorCorrection:
            scrapedIdxList = []
        for file in resultFileList:
            if args.errorCorrection:
                thisDF = pd.read_csv(f'./output/{file}', encoding='utf-8')
                if len(thisDF) == 0:
                    emptyResultIdx.append(int(file.split('.')[0]))
                if thisDF['helpful'].isna().sum() > 0:
                    invalidReactionIdx.append(int(file.split('.')[0]))
            else:
                scrapedIdxList.append(int(file.split('.')[0]))
        for idx, _ in targetResDF.iterrows():
            if mode == Mode.SEARCH:
                if args.errorCorrection:
                    if idx not in list(invalidIdxDict.keys()) + invalidReactionIdx + emptyResultIdx:
                        skipCnt += 1
                else:
                    if idx in scrapedIdxList:
                        skipCnt += 1

        if skipCnt > 0:
            logger.info(thisPrefix + f'Found the total {skipCnt} saved result(s).')
        targetSize = len(targetResDF) - skipCnt
        rIdx = -1
        ######################################
        ####### Part 2: Page File Load #######
        ######################################
        for _, (idx, res) in enumerate(targetResDF.iterrows()):
            failLog = ''
            if agent == Agent.CONCURRENCY and mode != Mode.OUTPUT_AUTO and mode != Mode.SEARCH:
                if not args.ignorePreviousReview:
                    if utils.existFinishedWorks(idx, args.cid, False):
                        skipCnt += 1
                        continue
                else:
                    existFinishedWork = utils.existFinishedWorks(idx, args.cid, True) # 이미 이전 리뷰 없이 수집 완료했는지
                    check = utils.checkDuplicatedWorks(idx, args.cid)
                    notExistWork = not check[0] # 수집한 적이 없는지
                    validReactionWork = check[1] # 정상적으로 Reaction이 수집되었었는지
                    if existFinishedWork or notExistWork or validReactionWork:
                        skipCnt += 1
                        continue

            if mode == Mode.SEARCH:
                if args.errorCorrection:
                    if idx not in list(invalidIdxDict.keys()) + invalidReactionIdx + emptyResultIdx:
                        continue
                else:
                    if idx in scrapedIdxList:
                        continue

            rIdx += 1
            if os.path.exists(f'./no_review_res/{idx}'):
                logger.info(thisPrefix + f'This restaurant has no review. Move on the next index.')
                continue
            
            if args.outputFolderName != 'output' and (os.path.exists(f'./final_res_valid/{idx}') or os.path.exists(f'./final_res_error/{idx}')):
                logger.info(thisPrefix + f'This index is already exmained.')
                continue
            
            thisPrefix = utils.setLoggerPrefix(args.cid, resInfo=(res['yelpid'], idx, targetSize, rIdx))
            elapsedTimeDict[idx] = []
            yelpIDinURL = res['yelpid']
            loadedYelpID = res['yelpid'] # 변경되기 전 기존 Yelp ID
            if os.path.exists(f'./yelpid_changed/{idx}.txt'):
                with open(f'./yelpid_changed/{idx}.txt', 'r') as f:
                    for line in f:
                        if line == '':
                            continue
                        yelpIDinURL = line.split(':')[1].strip()
                        loadedYelpID = yelpIDinURL
            
            st = time.time()
            if mode == Mode.SEARCH:
                if os.path.exists(f'./{outputFolderName}/{idx}.csv'):
                    # This condition is satisfied because the results have some errors.
                    # If the reviews were not to be found, they are excluded from the target review list.
                    # It includes only the results with HTTP response errors (e.g., 400, 422, ...)
                    # 1. Load the result file from the output folder
                    resultDF = pd.read_csv(f'./{outputFolderName}/{idx}.csv', encoding='utf-8')
                    # 2. Define the all page indices to be collected
                    allReviewIdx = list(searchDF[searchDF['yelpid'] == res['yelpid']].index)
                    # 3. Get the all page indices with HTTP response errors
                    collectedReviewIdx = resultDF['page_num'].unique().tolist()
                    noResultReviewIdx = []
                    emptyResultReviewIdx = []
                    if len(os.listdir('./final_no_result')) != 0:
                        noResultReviewIdx = [int(file.split('_')[1]) for file in os.listdir('./final_no_result') if int(file.split('_')[0]) == idx]
                    if len(os.listdir('./final_empty_result')) != 0:
                        emptyResultReviewIdx = [int(file.split('_')[1]) for file in os.listdir('./final_empty_result') if int(file.split('_')[0]) == idx]
                    notCollectedPageIdx = []
                    for aIdx in allReviewIdx:
                        if aIdx not in list(set(collectedReviewIdx + noResultReviewIdx + emptyResultReviewIdx)):
                            notCollectedPageIdx.append(aIdx)
                    invalidReactionPageIdx = []
                    if resultDF['helpful'].isna().sum() > 0:
                        invalidReactionPageIdx = resultDF[resultDF['helpful'].isna()]['page_num'].to_list()
                    reviewDict = searchDF.loc[notCollectedPageIdx + invalidReactionPageIdx, :].to_dict()
                    if len(reviewDict['yelpid']) == 0:
                        logger.info(thisPrefix + 'This index seems to be valid.')
                        thisPageIdxList = [file for file in os.listdir('./search_no_result') + os.listdir('./search_error') + os.listdir('./search_empty_result') if int(file.split('.')[0].split('_')[0]) == idx]
                        for file in thisPageIdxList:
                            if file in os.listdir('./search_no_result'):
                                os.remove(f'./search_no_result/{file}')
                            if file in os.listdir('./search_error'):
                                os.remove(f'./search_error/{file}')
                            if file in os.listdir('./search_empty_result'):
                                os.remove(f'./search_empty_result/{file}')
                        continue
                    if len(invalidReactionPageIdx) > 0:
                        resultDF = resultDF[~resultDF['page_num'].isin(invalidReactionPageIdx)].reset_index(drop=True)
                    thisRes = Restaurant(res['yelpid'], res['name'])
                    thisRes.initResFromDF(resultDF)
                else:
                    reviewDict = searchDF[searchDF['yelpid'] == res['yelpid']].to_dict()
                    thisRes = Restaurant(res['yelpid'], res['name'])
                newReviewDict = {}
                for key1, value1 in reviewDict.items():
                    if key1 == 'yelpid':
                        continue
                    for key2, _ in value1.items():
                        newReviewDict[key2] = {}
                        
                for key1, value1 in reviewDict.items():
                    if key1 == 'yelpid':
                        continue
                    for key2, value2 in value1.items():
                        if key1 not in newReviewDict[key2]:
                            newReviewDict[key2][key1] = {}
                        newReviewDict[key2][key1] = value2
                newReviewDict = dict(sorted(newReviewDict.items(), key=lambda item: item[0], reverse=True))
                idxDict[idx] = newReviewDict
                firstReviewIdx = list(idxDict[idx].keys())[-1]
                url = f'https://yelp.com/biz/{yelpIDinURL}?{urlencode({'q': utils.extractWords(idxDict[idx][firstReviewIdx]['review'])})}'
            else:
                if (idxDict[idx] is not None) and len(idxDict[idx]) > 0 and idxDict[idx][-1] > 0:
                    url = f'https://yelp.com/biz/{yelpIDinURL}?start={idxDict[idx][-1]}&sort_by=date_asc'
                else:
                    url = f'https://yelp.com/biz/{yelpIDinURL}?sort_by=date_asc'

                thisRes = Restaurant(res['yelpid'], res['name'])
                thisOriDF = None
                if mode == Mode.OUTPUT_AUTO and args.outputFolderName == 'output':
                    if idxDict[idx] is None or len(idxDict[idx]) > 0: # 특정 페이지만 수집해야하는 경우에만 레스토랑 인스턴스 초기화
                        thisOriDF = pd.read_csv(f'./{outputFolderName}/{utils.findOutputFileByIdx(idx, outputFolderName, mode)}', encoding='utf-8')
                        if len(thisOriDF) > 0:
                            if idxDict[idx] is not None:
                                pageList = [int(num / 10) + 1 for num in idxDict[idx]]
                                thisOriDF = thisOriDF[~thisOriDF['page_num'].isin(pageList)].reset_index(drop=True) # 수집하는 페이지를 가지는 행 삭제
                            thisRes.initResFromDF(thisOriDF)
        
            firstReviewInfo = None
            logger.info(thisPrefix + 'Scraping the first index...')
            if mode == Mode.SEARCH:
                pageIdx = firstReviewIdx
                firstReviewInfo = idxDict[idx][firstReviewIdx]
                thisHTML = YelpHTML(url, args.APIKey, args.retrialNum, False, firstReviewInfo)
            else:
                thisHTML = YelpHTML(url, args.APIKey, args.retrialNum, args.ignorePreviousReview)
            thisSoup = thisHTML.getSoup()
            if type(thisSoup) == int:
                if thisSoup == 404:
                    logger.error(thisPrefix + f'Page Not Found (Error 404).')
                elif thisSoup == -1:
                    logger.error(thisPrefix + f'Maximum Retrial Number Reached (Error -1).')
                else:
                    logger.error(thisPrefix + f'Error Occured (Error Code: {thisSoup})')
                failLog += f'{idx}: ERROR {thisSoup}'
                utils.writeLog('fail_log', failLog, args.cid, 'log' if not args.ignorePreviousReview else 'log_nopv')
                totDict['fail'].append(thisRes)
                if mode == Mode.SEARCH:
                    with open(f'./search_error/{idx}_{pageIdx}.txt', 'w') as f:
                        f.write(f'{idx}: ERROR {thisSoup}')
                continue
            
            # Redirection 해결
            # 주어진 Yelp ID로 만든 URL을 통해 접속할 때, Yelp ID가 변경되었다면 그것이 포함된 페이지로 Redirect됨.
            # Redirect된 URL로 다시 접속.
            # 그러나 Parsed된 HTML에서 추출한 새 URL 역시 여전히 현재 Yelp ID가 포함되지 않고, 과거 Yelp ID가 포함되어 있는 경우가 드물지 않게 있음.
            # 따라서, Parsed된 HTML에서 추출한 URL로 접속했을 때 추출한 Yelp ID가 변경되지 않을 때까지 반복.
            URLElement = thisSoup.find('meta', attrs={'data-rh': 'true', 'property': 'og:url'})
            if URLElement is not None:
                parsedURL = URLElement.get('content')
                if mode == Mode.SEARCH and parsedURL.find('?q=') == -1:
                    url = parsedURL + f'?q={utils.extractWords(firstReviewInfo['review'])}'
                    yelpIDinURL = parsedURL.split('/')[-1]
                    logger.info(thisPrefix + f'Found the different Yelp ID ({yelpIDinURL})')
                    clog = f'{idx}: {yelpIDinURL}'
                    with open(f'./yelpid_changed/{idx}.txt', 'w') as f:
                        f.write(clog)
                if mode != Mode.SEARCH and parsedURL.find('sort_by=date_asc') == -1: # Redirect 되어 주소 확인 필요.
                    url = parsedURL + '?sort_by=date_asc'
                    yelpIDinURL = parsedURL.split('/')[-1]
                    while yelpIDinURL != loadedYelpID:
                        logger.info(thisPrefix + f'Yelp ID in the parsed HTML ({yelpIDinURL}) is distinct with Yelp ID loaded ({loadedYelpID})')
                        logger.info(thisPrefix + f'Attempting to get the parsed HTML again...')
                        thisHTML = YelpHTML(url, args.APIKey, args.retrialNum, args.ignorePreviousReview)
                        thisSoup = thisHTML.getSoup()
                        if type(thisSoup) == int:
                            if thisSoup == 404:
                                logger.error(thisPrefix + f'Page Not Found (Error 404).')
                            elif thisSoup == -1:
                                logger.error(thisPrefix + f'Maximum Retrial Number Reached (Error -1).')
                            else:
                                logger.error(thisPrefix + f'Error Occured (Error Code: {thisSoup})')
                            failLog += f'{idx}: ERROR {thisSoup}'
                            utils.writeLog('fail_log', failLog, args.cid, 'log' if not args.ignorePreviousReview else 'log_nopv')
                            if mode == Mode.SEARCH:
                                with open(f'./search_error/{idx}_{pageIdx}.txt', 'w') as f:
                                    f.write(f'{idx}: ERROR {thisSoup}')
                            totDict['fail'].append(thisRes)
                            continue
                        logger.info(thisPrefix + f'Yelp ID in the parsed HTML: {yelpIDinURL}')
                        loadedYelpID = yelpIDinURL
                        URLElement = thisSoup.find('meta', attrs={'data-rh': 'true', 'property': 'og:url'})
                        parsedURL = URLElement.get('content')
                        yelpIDinURL = parsedURL.split('?')[0].split('/')[-1]
        
                    logger.info(thisPrefix + f'Found the different Yelp ID ({yelpIDinURL})')
                    clog = f'{idx}: {yelpIDinURL}'
                    url = f'https://yelp.com/biz/{yelpIDinURL}?sort_by=date_asc'
                    with open(f'./yelpid_changed/{idx}.txt', 'w') as f:
                        f.write(clog)

            thisPageNum = 1
            thisReviewInfo = None
            if args.outputFolderName != 'output' or (idxDict[idx] is None or len(idxDict[idx]) == 0):
                navigationElement = thisSoup.find('div', attrs={'aria-label': 'Pagination navigation'})
                totalPage = 0
                if navigationElement is not None:
                    totalPage = int(navigationElement.find_all('div', recursive=False)[1].find('span').text.split('of')[1])
                pageSequence = [i * 10 for i in range(totalPage - 1, 0, -1)] if totalPage > 0 else []
                if idxDict[idx] is None: # 정상 수집되었고, 이어서 수집하기 위해 pageSequence 구성
                    if args.outputFolderName != 'output':
                        thisOriDF = pd.read_csv(f'./{outputFolderName}/{utils.findOutputFileByIdx(idx, outputFolderName, mode)}', encoding='utf-8')
                    maxPage = int(thisOriDF['page_num'].max())
                    if args.outputFolderName != 'output':
                        if totalPage > maxPage:
                            logger.info(thisPrefix + f'Uncollected Pages Exists (Total - {totalPage}, Current Max - {maxPage})')
                            with open(f'./final_res_error/{idx}', 'w') as f:
                                pass
                            continue
                    if maxPage >= totalPage:
                        logger.info(thisPrefix + 'The reivews of this restaurant have been collected.')
                        if args.outputFolderName != 'output':
                            with open(f'./final_res_valid/{idx}', 'w') as f:
                                pass
                        continue
                    else:
                        if args.outputFolderName != 'output':
                            logger.info(thisPrefix + 'It has something wrong.')
                            with open(f'./final_res_error/{idx}', 'w') as f:
                                pass
                            continue
                    pageSequence = [i * 10 for i in range(totalPage - 1, maxPage - 1, -1)]
                    logger.info(thisPrefix + f'Found the results from {maxPage} pages. Trying to access the next page {maxPage + 1}.')
                    thisPageNum = pageSequence.pop()
                    thisPageNum = int(thisPageNum / 10) + 1
                    totalPage -= maxPage
                    url = f'https://yelp.com/biz/{yelpIDinURL}?start={int((thisPageNum - 1) * 10)}&sort_by=date_asc'
                    thisHTML = YelpHTML(url, args.APIKey, args.retrialNum, args.ignorePreviousReview)
                    thisSoup = thisHTML.getSoup()
                    if type(thisSoup) == int:
                        if thisSoup == 404:
                            logger.error(thisPrefix + f'Page Not Found (Error 404).')
                        elif thisSoup == -1:
                            logger.error(thisPrefix + f'Maximum Retrial Number Reached (Error -1).')
                        else:
                            logger.error(thisPrefix + f'Error Occured (Error Code: {thisSoup})')
                        failLog += f'{idx}: ERROR {thisSoup}'
                        utils.writeLog('fail_log', failLog, args.cid, 'log' if not args.ignorePreviousReview else 'log_nopv')
                        totDict['fail'].append(thisRes)
                        break
            else:
                totalPage = len(idxDict[idx])
                pageSequence = idxDict[idx]
                if mode == Mode.SEARCH:
                    thisPageNum, firstReviewInfo = pageSequence.popitem()
                else:
                    totalPage = len(idxDict[idx])
                    thisPageNum = pageSequence.pop()
                    thisPageNum = int(thisPageNum / 10) + 1

            # 페이지 정보 로드 완료
            rPageIdx = 0
            thisPrefix = utils.setLoggerPrefix(args.cid, resInfo=(res['yelpid'], idx, targetSize, rIdx), pageInfo=(thisPageNum, rPageIdx, totalPage, (mode == Mode.SEARCH)))
            #####################################################
            ############ Part 3: First Page Scrpaing ############
            #####################################################
            success = doScraping(thisSoup, thisRes, thisPageNum, args.ignorePreviousReview, firstReviewInfo)
            if success == -1:
                logger.info(thisPrefix + f'Yelp reports this restaurant has no review.')
                thisRes = Restaurant(res['yelpid'], res['name'])
                if not os.path.exists(f'./no_review_res/{idx}'):
                    with open(f'./no_review_res/{idx}', 'w') as f:
                        pass
                continue
            if success:
                if mode == Mode.OUTPUT_AUTO or mode == Mode.SEARCH:
                    outputDF = thisRes.toDataFrame()
                    outputDF.to_csv(f'./{outputFolderName}/{utils.findOutputFileByIdx(idx, outputFolderName, mode)}', encoding='utf-8', index=False)
            if success == -2:
                logger.info(thisPrefix + f'No search result. Move on the next review or page.')
                if os.path.exists(f'./search_empty_result/{idx}_{pageIdx}'):
                    with open(f'./final_empty_result/{idx}_{pageIdx}', 'w') as f:
                        pass
                else:
                    with open(f'./search_empty_result/{idx}_{pageIdx}', 'w') as f:
                        pass
            if success == -3:
                logger.info(thisPrefix + f'No matched result. Move on the next review or page.')
                if os.path.exists(f'./search_no_result/{idx}_{pageIdx}'):
                    with open(f'./final_no_result/{idx}_{pageIdx}', 'w') as f:
                        pass
                else:
                    with open(f'./search_no_result/{idx}_{pageIdx}', 'w') as f:
                        pass
            tryNum = 0
            fatalError = False
            while success == 0 and tryNum < args.retrialNum:
                tryNum += 1
                logger.info(thisPrefix + f'Not found any reviews on the page. Retrying... ({tryNum}/{args.retrialNum})')
                thisHTML = YelpHTML(url, args.APIKey, args.retrialNum, args.ignorePreviousReview, firstReviewInfo)
                thisSoup = thisHTML.getSoup()
                if type(thisSoup) == int:
                    if thisSoup == 404:
                        logger.error(thisPrefix + f'Index: {idx}, Yelp ID: {res['yelpid']} - Page Not Found (Error 404).')
                    elif thisSoup == -1:
                        logger.error(thisPrefix + f'Index: {idx}, Yelp ID: {res['yelpid']} - Maximum Retrial Number Reached (Error -1).')
                    else:
                        logger.error(thisPrefix + f'Index: {idx}, Yelp ID: {res['yelpid']} - Error Occured (Error Code: {thisSoup})')
                    failLog += f'{idx}: ERROR {thisSoup}'
                    utils.writeLog('fail_log', failLog, args.cid, 'log' if not args.ignorePreviousReview else 'log_nopv')
                    if mode == Mode.SEARCH:
                        if os.path.exists(f'./search_error/{idx}_{pageIdx}.txt'):
                            with open(f'./final_search_error/{idx}_{pageIdx}.txt', 'w') as f:
                                f.write(f'{idx}: ERROR {thisSoup}')
                        else:
                            with open(f'./search_error/{idx}_{pageIdx}.txt', 'w') as f:
                                f.write(f'{idx}: ERROR {thisSoup}')
                    totDict['fail'].append(thisRes)
                    break
                if idxDict[idx] is not None and len(idxDict[idx]) == 0:
                    navigationElement = thisSoup.find('div', attrs={'aria-label': 'Pagination navigation'})
                    totalPage = 0
                    if navigationElement is not None:
                        totalPage = int(navigationElement.find_all('div', recursive=False)[1].find('span').text.split('of')[1])
                    pageSequence = [i * 10 for i in range(totalPage - 1, 0, -1)] if totalPage > 0 else []

                if totalPage == 0:
                    continue
                success = doScraping(thisSoup, thisRes, thisPageNum, args.ignorePreviousReview, firstReviewInfo)
                if success and (mode == Mode.OUTPUT_AUTO or mode == Mode.SEARCH):
                    if mode == Mode.SEARCH:
                        if os.path.exists(f'./search_error/{idx}_{pageIdx}.txt'):
                            os.remove(f'./search_error/{idx}_{pageIdx}.txt')
                    outputDF = thisRes.toDataFrame()
                    outputDF.to_csv(f'./{outputFolderName}/{utils.findOutputFileByIdx(idx, outputFolderName, mode)}', encoding='utf-8', index=False)
                if success == -2:
                    logger.info(thisPrefix + f'No search result. Move on the next review or page.')
                    if os.path.exists(f'./search_empty_result/{idx}_{pageIdx}'):
                        with open(f'./final_empty_result/{idx}_{pageIdx}', 'w') as f:
                            pass
                    else:
                        with open(f'./search_empty_result/{idx}_{pageIdx}', 'w') as f:
                            pass
                    fatalError = True
                    break
                if success == -3:
                    logger.info(thisPrefix + f'No matched result. Move on the next review or page.')
                    if os.path.exists(f'./search_no_result/{idx}_{pageIdx}'):
                        with open(f'./final_no_result/{idx}_{pageIdx}', 'w') as f:
                            pass
                    else:
                        with open(f'./search_no_result/{idx}_{pageIdx}', 'w') as f:
                            pass
                    fatalError = True
                    break
            if fatalError:
                failLog += f'{idx}: ERROR -1'
                continue
            
            #####################################################
            ############## Part 4: Repeat Scraping ##############
            #####################################################
            invalidPageList = []
            while(True):
                if len(pageSequence) > 0:
                    rPageIdx += 1
                    if mode != Mode.SEARCH:
                        pageSequenceNum = pageSequence.pop()
                        thisPageNum = int(pageSequenceNum / 10) + 1 if rPageIdx > 0 else 0
                    else:
                        pageIdx, thisReviewInfo = pageSequence.popitem()
                        thisPageNum = pageIdx
                    thisPrefix = utils.setLoggerPrefix(args.cid, resInfo=(res['yelpid'], idx, targetSize, rIdx), pageInfo=(thisPageNum, rPageIdx, totalPage, (mode == Mode.SEARCH)))
                    logger.info(thisPrefix + 'Scraping the next page index...')
                    if rPageIdx > 0:
                        if mode != Mode.SEARCH:
                            url = f'https://yelp.com/biz/{yelpIDinURL}?start={int((thisPageNum - 1) * 10)}&sort_by=date_asc'
                        else:
                            
                            url = f'https://yelp.com/biz/{yelpIDinURL}?{urlencode({'q': utils.extractWords(thisReviewInfo['review'])})}'
                        thisHTML = YelpHTML(url, args.APIKey, args.retrialNum, args.ignorePreviousReview, thisReviewInfo)
                        thisSoup = thisHTML.getSoup()
                        if type(thisSoup) == int:
                            if thisSoup == 404:
                                logger.error(thisPrefix + f'Page Not Found (Error 404).')
                            elif thisSoup == -1:
                                logger.error(thisPrefix + f'Maximum Retrial Number Reached (Error -1).')
                            else:
                                logger.error(thisPrefix + f'Error Occured (Error Code: {thisSoup})')
                            failLog += f'{idx}: ERROR {thisSoup}'
                            invalidPageList.append(str(thisPageNum))
                            if mode == Mode.SEARCH:
                                if os.path.exists(f'./search_error/{idx}_{pageIdx}.txt'):
                                    with open(f'./final_search_error/{idx}_{pageIdx}.txt', 'w') as f:
                                        f.write(f'{idx}: ERROR {thisSoup}')
                                else:
                                    with open(f'./search_error/{idx}_{pageIdx}.txt', 'w') as f:
                                        f.write(f'{idx}: ERROR {thisSoup}')
                            continue
                        success = doScraping(thisSoup, thisRes, thisPageNum, args.ignorePreviousReview, thisReviewInfo)
                        if success and (mode == Mode.OUTPUT_AUTO or mode == Mode.SEARCH):
                            if mode == Mode.SEARCH:
                                if os.path.exists(f'./search_error/{idx}_{pageIdx}.txt'):
                                    os.remove(f'./search_error/{idx}_{pageIdx}.txt')
                            outputDF = thisRes.toDataFrame()
                            outputDF.to_csv(f'./{outputFolderName}/{utils.findOutputFileByIdx(idx, outputFolderName, mode)}', encoding='utf-8', index=False)
                        if success == -2:
                            logger.info(thisPrefix + f'No search result. Move on the next review or page.')
                            if os.path.exists(f'./search_empty_result/{idx}_{pageIdx}'):
                                with open(f'./final_empty_result/{idx}_{pageIdx}', 'w') as f:
                                    pass
                            else:
                                with open(f'./search_empty_result/{idx}_{pageIdx}', 'w') as f:
                                    pass
                            continue
                        if success == -3:
                            logger.info(thisPrefix + f'No matched result. Move on the next review or page.')
                            if os.path.exists(f'./search_no_result/{idx}_{pageIdx}'):
                                with open(f'./final_no_result/{idx}_{pageIdx}', 'w') as f:
                                    pass
                            else:
                                with open(f'./search_no_result/{idx}_{pageIdx}', 'w') as f:
                                    pass
                            continue
                        tryNum = 0
                        while not success and tryNum < args.retrialNum:
                            tryNum += 1
                            logger.info(f'Failed to obtain any reviews from the page. Retrying... ({tryNum}/{args.retrialNum})')
                            thisHTML = YelpHTML(url, args.APIKey, args.retrialNum, args.ignorePreviousReview, thisReviewInfo)
                            thisSoup = thisHTML.getSoup()
                            if type(thisSoup) == int:
                                if thisSoup == 404:
                                    logger.error(thisPrefix + f'Page Not Found (Error 404).')
                                elif thisSoup == -1:
                                    logger.error(thisPrefix + f'Maximum Retrial Number Reached (Error -1).')
                                else:
                                    logger.error(thisPrefix + f'Error Occured (Error Code: {thisSoup})')
                                failLog += f'{idx}: ERROR {thisSoup}'
                                invalidPageList.append(str(thisPageNum))
                                if os.path.exists(f'./search_error/{idx}_{pageIdx}.txt'):
                                    with open(f'./final_search_error/{idx}_{pageIdx}.txt', 'w') as f:
                                        f.write(f'{idx}: ERROR {thisSoup}')
                                else:
                                    with open(f'./search_error/{idx}_{pageIdx}.txt', 'w') as f:
                                        f.write(f'{idx}: ERROR {thisSoup}')
                                fatalError = True
                                break
                            success = doScraping(thisSoup, thisRes, thisPageNum, args.ignorePreviousReview, thisReviewInfo)
                            if success and (mode == Mode.OUTPUT_AUTO or mode == Mode.SEARCH):
                                if mode == Mode.SEARCH:
                                    if os.path.exists(f'./search_error/{idx}_{pageIdx}.txt'):
                                        os.remove(f'./search_error/{idx}_{pageIdx}.txt')
                                outputDF = thisRes.toDataFrame()
                                outputDF.to_csv(f'./{outputFolderName}/{utils.findOutputFileByIdx(idx, outputFolderName, mode)}', encoding='utf-8', index=False)
                            if success == -2:
                                logger.info(thisPrefix + f'No search result. Move on the next review or page.')
                                if os.path.exists(f'./search_empty_result/{idx}_{pageIdx}'):
                                    with open(f'./final_empty_result/{idx}_{pageIdx}', 'w') as f:
                                        pass
                                else:
                                    with open(f'./search_empty_result/{idx}_{pageIdx}', 'w') as f:
                                        pass
                                fatalError = True
                                break
                            if success == -3:
                                logger.info(thisPrefix + f'No matched result. Move on the next review or page.')
                                if os.path.exists(f'./search_no_result/{idx}_{pageIdx}'):
                                    with open(f'./final_no_result/{idx}_{pageIdx}', 'w') as f:
                                        pass
                                else:
                                    with open(f'./search_no_result/{idx}_{pageIdx}', 'w') as f:
                                        pass
                                fatalError = True
                                break
                        if fatalError:
                            continue
                else:
                    totDict['success'].append(thisRes)
                    if len(invalidPageList) == 0:
                        with open(f'./search_valid/{idx}', 'w') as f:
                            pass
                    et = time.time()
                    thisPrefix = utils.setLoggerPrefix(args.cid, resInfo=(res['yelpid'], idx, targetSize, rIdx))
                    elapsedTimeDict[idx].append(et - st)
                    if totalPage > 0:
                        logger.info(thisPrefix + f'Done. Total {thisRes.getNumReviews()} has been scraped.')
                        logger.info(thisPrefix + f'Elapsed Time: {utils.formatSec(elapsedTimeDict[idx][-1])}, Average Elpased Time per Page: {utils.formatSec(elapsedTimeDict[idx][-1] / totalPage)}')
                    if mode != Mode.OUTPUT_AUTO and mode != Mode.SEARCH:
                        logger.info(thisPrefix + f'Saving the result to the csv file...')
                        # 저장 경로 설정
                        basePath = f'./{outputFolderName}'
                        agentPath = '' if agent != Agent.CONCURRENCY else f'/Concurrency {args.cid}'
                        filePath = basePath + agentPath
                        if not os.path.exists(filePath):
                            os.makedirs(filePath)
                        # 저장 파일 이름 설정
                        baseFileName = f'{idx}'
                        timeName = f'_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")[:-3]}'
                        cidName = '' if agent != Agent.CONCURRENCY else f'_CONCURRENCY_{args.cid}'
                        idxRange = '' if mode != Mode.INDEX_RANGE else f'_INDEX_RANGE_{idxList[0]}_{idxList[-1]}'
                        idxNum = '' if mode != Mode.SELECTION else f'_SELECTION_{len(idxList)}'
                        fileName = baseFileName + timeName + cidName + idxRange + idxNum + '.csv'
                        outputDF = thisRes.toDataFrame()
                        fullFilePath = filePath + '/' + fileName
                        outputDF.to_csv(fullFilePath, encoding='utf-8', index=False)

                        if len(invalidPageList) > 0:
                            failLog += f'{idx}: {', '.join(invalidPageList)}\n'
                            if failLog != '':
                                logger.info('Saving the log for the fails...')
                                utils.writeLog('fail_log', failLog, args.cid, 'log' if not args.ignorePreviousReview else 'log_nopv')

                    logger.info(thisPrefix + f'Cumulative call counts: {YelpHTML.callNum}, Estimated costs: ${YelpHTML.callNum * 0.00208329:.3f}')
                    remainingResNum = len(targetResDF) - (rIdx + 1)
                    cumlElapsedTime = [val for sublist in elapsedTimeDict.values() for val in sublist]
                    averageElapsedTime = np.mean(cumlElapsedTime)
                    if rIdx + 1 != targetSize:
                        logger.info(thisPrefix + f'Estimated Remaining Time to Finish: {utils.formatSec(remainingResNum * averageElapsedTime)}')
                    break

        if len(totDict) == 0:
            logger.info('Nothing to do. The program will be terminated.')
        else:
            logger.info('===============================================')
            logger.info(('' if agent != Agent.CONCURRENCY else f'Concurrency #{args.cid}: ') + 'Scrapping has been completed.')
            logger.info('===============================================')
            logger.info(f'Total Number of Restaurants: {targetSize}')
            successNum = len(totDict['success'])
            failNum = len(totDict['fail'])
            logger.info(f'Success: {successNum}')
            logger.info(f'Fail: {failNum}')
            totElapsedTime = [val for sublist in elapsedTimeDict.values() for val in sublist]
            totalElapsedTime = np.sum(totElapsedTime)
            logger.info(f'Total Elapsed Time: {utils.formatSec(totalElapsedTime)}')
            logger.info(f'Total estimated costs: ${YelpHTML.callNum * 0.00208329:.3f}')
            logger.info('===============================================')
            logger.info('Done. Requested jobs has been finished. The program will be terminated.')

if __name__ == '__main__':
    if not os.path.exists(args.targetList + '.csv'):
        logger.error(args.targetList + '.csv cannot be found.')
        exit()

    parserError = False

    agent = Agent.SINGLE
    if args.cid != -1:
        if not (1 <= args.cid <= 200):
            parser.error(f'Invalid concurrency ID: Concurrecny ID is out of range.')
            exit()
        if not parserError:
            agent = Agent.CONCURRENCY
            indexTuple = utils.getIndexListForConcurrency(args.cid)
            defaultMinIdx = indexTuple[0]
            defaultMaxIdx = indexTuple[1]
            print(indexTuple)
            logger.info(f'Activated Concurrency #{args.cid}.')

    if agent == Agent.CONCURRENCY and args.yelpid != '':
        logger.error('Cannot designate yelp ID in concurrency mode.')
        exit()

    mode = Mode.UNDEFINED
    duplicated = False
    if os.path.exists(args.indexListFile):
        mode = Mode.SELECTION
    elif os.path.exists(args.searchFile):
        mode = Mode.SEARCH
    else:
        if len(os.listdir(f'./{args.outputFolderName}')) != 0:
            if mode != Mode.UNDEFINED:
                duplicated = True
            else:
                mode = Mode.OUTPUT_AUTO
        if args.yelpid != '':
            if mode != Mode.UNDEFINED:
                duplicated = True
            else:
                mode = Mode.ONE_URL
        if args.minIdx != -1:
            if mode != Mode.UNDEFINED:
                duplicated = True
            else:
                mode = Mode.INDEX_RANGE

    if duplicated:
        trig = []
        if len(os.listdir(f'./{args.outputFolderName}')) != 0:
            trig.append('The output folder is not empty.')
        if os.path.exists(args.indexListFile):
            trig.append('Exsting the index list file')
        if args.yelpid != '':
            trig.append('Specified the URL')
        if args.minIdx != -1:
            trig.append('Speficied the min index.')
        logger.error(f'The program mode cannot be duplicated. Please check the following: {', '.join(trig)}')
        exit()

    if mode == Mode.SELECTION:
        selectionDict = utils.loadSectionModeFile(args.indexListFile)
        if len(selectionDict) == 0:
            logger.error('The index list file is empty or invalid.')
            exit()
        # 레스토랑 인덱스 범위 검증.
        sortedIndexList = sorted(list(selectionDict.keys()))
        # 1. 인덱스 값이 모두 정수값인지.
        for idx in sortedIndexList:
            if type(idx) != int:
                logger.error('Please check the index list file. Index file includes the non-integer index.')
                exit()
        # 2. 최대/최소 인덱스 값이 범위가 맞는지.
        invalidBound = False
        trig = []
        idx0 = sortedIndexList[0]
        idxLB = defaultMinIdx if agent == Agent.CONCURRENCY else 0
        if (idx0 < idxLB):
            invalidBound = True
            trig.append('Min index')
        
        if agent == Agent.CONCURRENCY:
            idx1 = sortedIndexList[-1]
            idxUB = defaultMaxIdx if agent == Agent.CONCURRENCY else args.maxIdx
            if (idx1 > idxUB):
                invalidBound = True
                trig.append('Max index')
        if invalidBound:
            logger.error(f'Please check the index list file. The following index is out of range: {', '.join(trig)}')
        # 3. 지정한 페이지 리스트가 비어있거나, 리스트 내 페이지 수가 모두 정수값이고, 1보다 큰지.
        existInvalidPageNum = False
        for resIdx, pageList in selectionDict.items():
            invalidPageNum = False
            # 페이지 리스트가 비어있는 경우 모든 페이지 탐색이므로 생략.
            if len(pageList) == 0:
                continue
            nonIntegerPageList = []
            outOfRangePageList = []
            for page in pageList:
                if type(page) != int:
                    invalidPageNum = True
                    existInvalidPageNum = True
                    nonIntegerPageList.append(str(page))
                else:
                    if page < 1:
                        invalidPageNum = True
                        existInvalidPageNum = True
                        outOfRangePageList.append(str(page))
            if invalidPageNum:
                logger.error(f'Please check the index file: The restaurant index {resIdx} includes invalid page number(s): {', '.join(nonIntegerPageList + outOfRangePageList)}')
        if invalidBound or existInvalidPageNum:
            exit()

    if mode == Mode.INDEX_RANGE:
        if args.minIdx < 0:
            parserError = True
            parser.error('Min index cannot be negative.')

        if args.maxIdx != -1 and args.maxIdx < 0:
            parserError = True
            parser.error('Max index must be equal to -1 (default) or non-negative.')

        if (args.maxIdx != -1) and (args.minIdx > args.maxIdx):
            parserError = True
            parser.error('Min index cannot be larger than max index.')
            
        if agent == Agent.CONCURRENCY:
            if (args.minIdx < defaultMinIdx) or (args.maxIdx > defaultMaxIdx):
                parserError = True
                parser.error(f'Please check the index range you provided. It is out of range to which concurrency agent {args.cid} is designated.')

    if parserError:
        logger.error('Some arguments are not valid.')
        exit()

    if mode == Mode.UNDEFINED:
        if agent != Agent.CONCURRENCY:
            logger.error('Cannot define the mode. Please be specified the arugments or check the relevant files.')
            exit()
        else:
            mode = Mode.INDEX_RANGE

    idxDict = {}
    if mode == Mode.INDEX_RANGE or mode == Mode.SEARCH:
        minIdx = args.minIdx if agent != Agent.CONCURRENCY else defaultMinIdx
        maxIdx = args.maxIdx if agent != Agent.CONCURRENCY else defaultMaxIdx
        if mode == Mode.INDEX_RANGE:
            if minIdx < maxIdx:
                idxDict = {i: [] for i in range(minIdx, maxIdx + 1)}
            else:
                idxDict = {minIdx: []}
        else:
            if minIdx < maxIdx:
                idxDict = {i: {} for i in range(minIdx, maxIdx + 1)}
            else:
                idxDict = {minIdx: {}}
    if mode == Mode.SELECTION:
        idxDict = utils.loadSectionModeFile(args.indexListFile)
        # URL에 입력되는 형태로 페이지 번호 변환
        for idx in idxDict.keys():
            idxDict[idx] = [(value - 1) * 10 for value in idxDict[idx]]
        if args.maxIdx > -1:
            logger.warning('Max index in the arugments is ignored because selection mode is activated.')
    if mode == Mode.OUTPUT_AUTO:
        outputDict = utils.getOutputFileDict(args.outputFolderName)
        indexList = list(outputDict.keys())
        if agent == Agent.CONCURRENCY:
            # indexList 200개 균등 분배.
            indexChunkList = utils.chunkList(indexList, 200)
            if len(indexChunkList) < args.cid:
                logger.error('This concurrency has nothing to do.')
                exit()
            else:
                outputDict = {idx: fileName for idx, fileName in outputDict.items() if idx in indexChunkList[args.cid - 1]}
        for idx, fileName in outputDict.items():
            if args.outputFolderName != 'output':
                if str(idx) in os.listdir('./final_res_valid'):
                    logger.info(f'Index {idx} - It is comfirmed to be valid.')
                    continue
                if str(idx) in os.listdir('./final_res_error'):
                    logger.info(f'Index {idx} - It is comfiremd to have some errors.')
                    continue
            oriDF = pd.read_csv(f'./{args.outputFolderName}/{fileName}', encoding='utf-8')
            invalidTypeList = utils.checkValidity(idx, oriDF)
            # 중복된 리뷰가 있을 경우, 그것들을 제거하고 다시 InvalidTypeList 계산
            # 리뷰 작성 일자를 오름차순 정렬 후 단조 증가 한 경우가 같이 포함되어 있는 경우는 제외.
            if len(invalidTypeList) == 1 and utils.InvalidType.DUPLICATED_REVIEW in invalidTypeList:
                oriDF = oriDF.drop_duplicates(subset=['userid', 'rating', 'rating_date', 'review', 'is_previous_review'])
                oriDF.to_csv(f'./{args.outputFolderName}/{fileName}', encoding='utf-8')
                invalidTypeList = utils.checkValidity(idx, oriDF)
            if len(invalidTypeList) == 0:
                idxDict[idx] = None # List가 아닌 None으로 설정하여, 정상 수집된 것은 이미 수집한 것을 다시 수집하지 않도록 설정
                continue
            else:
                pageList = []
                for _, thisPageList in invalidTypeList:
                    if len(thisPageList) == 0:
                        pageList = []
                        break
                    else:
                        pageList += thisPageList
                if len(pageList) > 0:
                    if args.outputFolderName != 'output':
                        pageList = [page for page in pageList if not np.isnan(page)]
                    pageList = list(map(int, pageList))
                    pageList = sorted(list(set(pageList)), reverse=True)
                idxDict[idx] = pageList
        # URL에 입력되는 형태로 페이지 번호 변환
        for idx in idxDict.keys():
            if idxDict[idx] is not None and len(idxDict[idx]) > 0:
                idxDict[idx] = [(value - 1) * 10 for value in idxDict[idx]]

    print(idxDict)
    outputFolderName = 'output' if not args.ignorePreviousReview else 'output_nopv'
    scrape(args, agent, mode, idxDict, args.outputFolderName)