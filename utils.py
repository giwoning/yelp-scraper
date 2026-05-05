import pandas as pd
import os
import time
import numpy as np
import re
from datetime import datetime
import shutil
from dateutil import parser
from enum import Enum, auto

from model.review import Restaurant
from scrapper import Mode

class InvalidType(Enum):
    EXCESS_REVIEW_NUM = auto()
    NO_REVIEW = auto()
    OMITTED_PAGE = auto()
    EMPTY_REACTION = auto()
    DUPLICATED_REVIEW = auto()
    NON_MONOTONIC_INC_DATE = auto()

    @property
    def label(self):
        displayNames = {
            InvalidType.EXCESS_REVIEW_NUM: 'Excess Review Numbers',
            InvalidType.NO_REVIEW: 'No Review',
            InvalidType.OMITTED_PAGE: 'Not Scrapped Pages Exist',
            InvalidType.EMPTY_REACTION: 'Not Scrapped Reactions Exist',
            InvalidType.DUPLICATED_REVIEW: 'Duplicated Reviews Exist',
            InvalidType.NON_MONOTONIC_INC_DATE: 'Rating Dates are not Monotonic Increasing'
        }
        return displayNames.get(self, self.name)

# cid: Curruency ID
# resInfoList: (yelpid, targetNum, idx, ridx)
## yelpid: Yelp ID
## targetNum: Total number of target restuarants
## idx: Restrauant Absoulte Index
## ridx: Restrauant Relative Index
# pageInfoList: (pageIdx, rPageIdx, targetPageNum)
## pageIdx: Page Absoulte Index (For search mode, it refers to Review Index)
## rPageIdx: Page Relative Index
## targetPageNum: Total number of the pages in a target restuarnt
## searchMode: True if search mode False otherwise
def setLoggerPrefix(cid:int, resInfo: tuple=None, pageInfo: tuple=None):
    if resInfo is None:
        yelpid, idx, targetNum, ridx = None, None, None, None
    else:
        yelpid, idx, targetNum, ridx = resInfo
    if pageInfo is None:
        pageIdx, rPageIdx, targetPageNum, searchMode = None, None, None, None
    else:
        pageIdx, rPageIdx, targetPageNum, searchMode = pageInfo
    prefix = ''
    if cid != -1:
        if resInfo is None and pageInfo is None:
            return f'Concurrency #{cid}: '
        else:
            prefix += f'Concurrency #{cid}, '
    if resInfo is not None:
        if targetPageNum == -1:
            return f'Index: {idx}, Yelp ID: {yelpid}: '
        else:
            if pageInfo is not None:
                prefix += f'Index: {idx}, Yelp ID: {yelpid} ({ridx + 1}/{targetNum}), '
            else:
                return prefix + f'Index: {idx}, Yelp ID: {yelpid} ({ridx + 1}/{targetNum}): '
    if pageInfo is not None:
        if searchMode:
            prefix += f'Review Index: {pageIdx} ({rPageIdx + 1}/{targetPageNum}): '
        else:
            rPageIdxPrint = 'Home' if pageIdx == 0 else rPageIdx + 1
            prefix += f'Page Number: {pageIdx} ({rPageIdxPrint}/{targetPageNum}): '
    return prefix
    
def loadSectionModeFile(path: str) -> dict:
    selectionDict = {}
    error = False
    if os.path.exists(path):
        with open(path, 'r') as file:
            for line in file:
                if line == '':
                    continue
                parts = line.strip().split(':')
                try:
                    resIndex = int(parts[0])
                except:
                    print(f'Failed to convert the index into the integer value: {parts[0].strip()}')
                    error = True
                    break
                if parts[1].find('ERROR') != -1:
                    selectionDict[resIndex] = []
                else:
                    if parts[1].strip() == '':
                        selectionDict[resIndex] = []
                    else:
                        try:
                            for page in parts[1].split(','):
                                pageNum = int(page)
                        except:
                            print(f'Failed to convert the page number into the integer value: {page.strip()}')
                            error = True
                            break
                        resPageList = list(map(int, parts[1].split(',')))
                        selectionDict[resIndex] = resPageList
    if error:
        return {}
    return selectionDict
    
def formatSec(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    if hours > 0:
        return '{}h {}m {:.2f}s'.format(hours, minutes, secs)
    elif minutes > 0:
        return '{}m {:.2f}s'.format(minutes, secs)
    else:
        return '{:.2f}s'.format(secs)

def aggResDF(resList: list[Restaurant]):
    exportDF = pd.DataFrame()
    for res in resList:
        resDF = res.toDataFrame()
        exportDF = pd.concat([exportDF, resDF])
    return exportDF

def getIndexListForConcurrency(concurrencyID, totalItems=465, numConcurrency=200):
    numbers = list(range(0, totalItems))
    avgSize = len(numbers) / numConcurrency
    totalList = [numbers[int(i * avgSize): int((i + 1) * avgSize)] for i in range(numConcurrency)]
    return (totalList[concurrencyID - 1][0], totalList[concurrencyID - 1][-1])

def checkDuplicatedWorks(idx:int, concurrencyID: int):
    existWork = False
    for i in range(1, 151):
        lb = getIndexListForConcurrency(i, numConcurrency=150)[0]
        ub = getIndexListForConcurrency(i, numConcurrency=150)[1]
        if lb <= idx <= ub:
            concurrencyID = i
            break
    folderPath = f'./output/Concurrency {concurrencyID}'
    matchedFiles = [file for file in os.listdir(folderPath) if f'CONCURRENCY_{concurrencyID}' in file]
    targetFiles = []
    if len(matchedFiles) > 0:
        collectedIndexList = [int(fileName.split('_')[0]) for fileName in matchedFiles] 
        for i, thisIndex in enumerate(collectedIndexList):
            if idx == thisIndex:
                existWork = True
                targetFiles.append(matchedFiles[i])
    
        existValidReactionValue = False
        if existWork:
            if len(targetFiles) > 1:
                timestampDict = {}
                for file in targetFiles:
                    match = re.compile(r"(\d+)_([\d]{4}-[\d]{2}-[\d]{2}_[\d]{2}-[\d]{2}-[\d]{2}-[\d]+)_CONCURRENCY_(\d+)_INDEX_RANGE_(\d+)_(\d+)\.csv").match(file)
                    if match:
                        timestamp = match.group(2)
                        timestampDict[file] = datetime.strptime(timestamp, '%Y-%m-%d_%H-%M-%S-%f')
                
                targetFile = max(timestampDict, key=timestampDict.get)
            else:
                targetFile = targetFiles[0]

            thisDF = pd.read_csv(folderPath + '/' + targetFile, encoding='utf-8')
            helpful = thisDF[thisDF['is_previous_review'] == 0]['helpful']
            if len(helpful) == 0 or not np.isnan(helpful[0]):
                existValidReactionValue = True
        return (existWork, existValidReactionValue)
    return existWork

def existFinishedWorks(idx:int, concurrencyID:int, ignorePreviousReview:bool):
    found = False
    folderName = 'output' if not ignorePreviousReview else 'output_nopv'
    folderPath = f'./{folderName}/Concurrency {concurrencyID}'
    if not os.path.exists(folderPath):
        os.makedirs(folderPath)
        return found
    matchedFiles = [file for file in os.listdir(folderPath) if f'CONCURRENCY_{concurrencyID}' in file]
    if len(matchedFiles) > 0:
        collectedIndexList = [int(fileName.split('_')[0]) for fileName in matchedFiles]
        for thisIndex in collectedIndexList:
            if idx == thisIndex:
                found = True
    return found

def writeLog(baseFileName: str, log: str, concurrencyID: int=None, folderName:str='log'):
    timeName = f'_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")[:-3]}'
    concurrencyName = '' if concurrencyID == -1 else f'_from_concurrency_{concurrencyID}'
    failLogFileName = baseFileName + timeName + concurrencyName + '.txt'
    with open(f'./{folderName}/{failLogFileName}', 'w') as file:
        file.writelines(log)
        
def getOutputFileDict(outputFolderName:str):
    outputPath = f'./{outputFolderName}'
    outputDict = {}
    # 중복 삭제
    #pattern = re.compile(r'(\d+)_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}-\d+)_SELECTION_(\d+)\.csv')
    outputFileList = [file for file in os.listdir(outputPath)]
    for file in outputFileList:
        outputDict[int(file.split('_')[1].split('.')[0])] = file
        """
        match = pattern.match(file).groups()
        idx = int(match[0])
        if match:
            if idx not in outputDict:
                outputDict[idx] = file
            else:
                fileTimestampStr = match[1]
                fileTimestamp = datetime.strptime(fileTimestampStr, '%Y-%m-%d_%H-%M-%S-%f').timestamp()
                thisFileName = outputDict[idx]
                thisTimestampStr = pattern.match(thisFileName).groups()[1]
                thisTimestamp = datetime.strptime(thisTimestampStr, '%Y-%m-%d_%H-%M-%S-%f').timestamp()
                if fileTimestamp > thisTimestamp:
                    shutil.move(f'./output/{outputDict[idx]}', f'./output_temp/{outputDict[idx]}')
                    outputDict[idx] = file
        """
    if len(outputDict) > 0:
        outputDict = dict(sorted(outputDict.items(), key=lambda x: x[0]))
    return outputDict

# By ChatGPT
def chunkList(lst, numChunks):
    if numChunks > len(lst):
        numChunks = len(lst)  # 빈 리스트 방지
        
    avgSize = len(lst) // numChunks
    remainder = len(lst) % numChunks

    chunks = []
    start = 0
    for i in range(numChunks):
        extra = 1 if i < remainder else 0  # 앞에서 remainder 개수만큼 1개씩 더 분배
        end = start + avgSize + extra
        chunks.append(lst[start:end])
        start = end

    return chunks

def findOutputFileByIdx(idx: int, outputFolderName: str, mode:Mode=Mode.OUTPUT_AUTO):
    if mode == Mode.OUTPUT_AUTO:
        outputFiles = [file for file in os.listdir(f'./{outputFolderName}') if int(file.split('_')[1].split('.')[0]) == idx]
        if len(outputFiles) > 1:
            print('[WARNING] The index has more than one output file.')
        return outputFiles[0]
    else:
        return f'{idx}.csv'

def checkValidity(idx, df: pd.DataFrame, verbose=False) -> list[tuple]:
    # 리뷰가 없거나 page_num 칼럼이 없는 경우.
    if len(df) == 0 or (not 'page_num' in df.columns):
        if verbose:
            print(f'Index {idx} - {InvalidType.NO_REVIEW.label}')
        return [(InvalidType.NO_REVIEW, [])]

    # (InvalidType, InvalidPage)의 순서쌍 리스트.
    # InvalidPage가 None이 아닌 비어있는 경우 모든 페이지를 의미.
    invalidTypeList = []
    if 'page_num' in df.columns:
        # 동일 유저가 과거에 작성된 리뷰를 제외하고, 수집된 리뷰가 10개를 초과하는 페이지가 존재하는 경우.
        pageNumCnt = [(page, cnt) for (page, cnt) in df[df['is_previous_review'] == 0]['page_num'].value_counts().to_dict().items() if cnt > 10]
        if len(pageNumCnt) > 0:
            invalidTypeList.append((InvalidType.EXCESS_REVIEW_NUM, [])) 

        pageNumList = [int(pageNum) for pageNum in df['page_num'].to_list() if not np.isnan(pageNum)]
        unscrappedPageList = []
        # 수집하지 않은 페이지가 존재할 경우.
        startPage = 1
        endPage = max(pageNumList)
        for page in range(startPage, endPage + 1):
            if page not in pageNumList:
                unscrappedPageList.append(str(page))
        
        if len(unscrappedPageList) > 0:
            if verbose:
                print(f'Index {idx} - 수집되지 않은 페이지 리스트: {', '.join(unscrappedPageList)}')
            invalidTypeList.append((InvalidType.OMITTED_PAGE, unscrappedPageList))
        
        # 리뷰 남긴 일자를 오름차순 정렬했을 때, 단조 증가가 아닌 경우.
        df['rating_date'] = df['rating_date'].apply(parser.parse)
        if not df[df['is_previous_review'] == 0].sort_values(by=['page_num', 'rating_date'])['rating_date'].is_monotonic_increasing:
            invalidTypeList.append((InvalidType.NON_MONOTONIC_INC_DATE, []))

    # Reaction이 수집되지 않은 경우.
    if df['helpful'].isna().sum() > 0:
        unscrappedReactionPageList = df[df['helpful'].isna()]['page_num'].unique().tolist()
        invalidTypeList.append((InvalidType.EMPTY_REACTION, unscrappedReactionPageList))
        
    # 리뷰가 반복해서 등장하는 경우
    if df.duplicated(subset=['userid', 'rating_date', 'rating', 'review', 'is_previous_review']).sum() > 0:
        thisType = InvalidType.DUPLICATED_REVIEW
        invalidTypeList.append((thisType, []))
    
    if verbose and len(invalidTypeList) > 0:
        invalidTypeLabelList = [thisType.label for thisType in invalidTypeList]
        print(f'Index {idx} - {', '.join(invalidTypeLabelList)}')

    return invalidTypeList

def extractWords(text, maxWords=20):
    words = text.split()
    if len(words) < maxWords:
        maxWords = len(words)
    return " ".join(words[:maxWords]).replace('\\n', '')