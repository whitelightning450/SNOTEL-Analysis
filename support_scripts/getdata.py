#general packages
import numpy as np
import pandas as pd
import ulmo
import streamstats

#packages to load AWS data
import boto3
import os
from botocore import UNSIGNED 
from botocore.client import Config
import os
os.environ['AWS_NO_SIGN_REQUEST'] = 'YES'

import warnings
warnings.filterwarnings("ignore")

#Set Global Variables
ACCESS_KEY = pd.read_csv('AWSaccessKeys.csv')

#AWS Data Connectivity
#start session
SESSION = boto3.Session(
    aws_access_key_id=ACCESS_KEY['Access key ID'][0],
    aws_secret_access_key=ACCESS_KEY['Secret access key'][0]
)
s3 = SESSION.resource('s3')

BUCKET_NAME = 'national-snow-model'
BUCKET = s3.Bucket(BUCKET_NAME) 
S3 = boto3.resource('s3')

def AWSSnotel(state):
    files =[]
    for object_summary in BUCKET.objects.filter(Prefix=f"SNOTEL/{state}/"):
        files.append(object_summary.key)

    files.remove(f"SNOTEL/{state}/")
    cols = ['sitename',	'elev_ft',	'median_peak_in',	'median_peak_date']
    regions = {}
    keyslice = len(f"SNOTEL/{state}/")
    print('Collecting data for the following regions:')
    for key in files:
        print(key[keyslice:-5])
        name = key[keyslice:-5]
        obj = BUCKET.Object(key)
        body = obj.get()['Body']
        regions[name] = pd.read_excel(body.read())
        regions[name].rename(columns ={'Basin':'sitename','Elev':'elev_ft',
                                'Unnamed: 4':'median_peak_in', 'Unnamed: 5':'median_peak_date'}, inplace = True)
        regions[name] = regions[name][cols]
        regions[name] = regions[name].loc[3:]
        regions[name]['median_peak_in'] =  regions[name]['median_peak_in'].str.replace(r"\(.*?\)", "", regex=True)

        try:
            #Mar peaks
            Peak = regions[name][regions[name]['median_peak_date'].str.contains("Mar", na=False)]
            Peak['median_peak_date'] =  Peak['median_peak_date'].str.replace(r"\(.*?\)", "", regex=True)
            Peak['peak_day'] = Peak['median_peak_date'].apply(lambda x: x[-2:])
            Peak['median_peak_date'] = pd.to_datetime('2024-03-'+ Peak['peak_day']+' '+'00:00:00')
            regions[name].update(Peak)

            #Apr peaks
            Peak = regions[name][regions[name]['median_peak_date'].str.contains("Apr", na=False)]
            Peak['median_peak_date'] =  Peak['median_peak_date'].str.replace(r"\(.*?\)", "", regex=True)
            Peak['peak_day'] = Peak['median_peak_date'].apply(lambda x: x[-2:])
            Peak['median_peak_date'] = pd.to_datetime('2024-04-'+ Peak['peak_day']+' '+'00:00:00')
            regions[name].update(Peak)
        except:
            print('All dates in datetime')
        regions[name].replace(u'\xa0',u'', regex=True, inplace=True)

    return regions


def SNOTELmeta(SNOTEL):
    #get metadata
    key = 'SNOTEL/ground_measures_metadata.csv'
    obj = BUCKET.Object(key)
    body = obj.get()['Body']
    GF = pd.read_csv(body)
    GF.rename(columns={'name':'sitename'}, inplace=True)

    for basin in SNOTEL.keys():
        SNOTEL[basin] =pd.merge(SNOTEL[basin], GF, how='left', on ='sitename')

    return SNOTEL


def get_SNOTEL(sitecode, start_date, end_date):
        print(sitecode)

        # This is the latest CUAHSI API endpoint
        wsdlurl = 'https://hydroportal.cuahsi.org/Snotel/cuahsi_1_1.asmx?WSDL'

        # Daily SWE
        variablecode = 'SNOTEL:WTEQ_D'

        try:
            # Request data from the server
            site_values = ulmo.cuahsi.wof.get_values(wsdlurl, sitecode, variablecode, start=start_date, end=end_date)
            #end_date = end_date.strftime('%Y-%m-%d')
            # Convert to a Pandas DataFrame
            SNOTEL_SWE = pd.DataFrame.from_dict(site_values['values'])
            # Parse the datetime values to Pandas Timestamp objects
            SNOTEL_SWE['datetime'] = pd.to_datetime(SNOTEL_SWE['datetime'], utc=True).values
            SNOTEL_SWE.set_index('datetime', inplace = True)
            # Convert values to float and replace -9999 nodata values with NaN
            SNOTEL_SWE['value'] = pd.to_numeric(SNOTEL_SWE['value']).replace(-9999, np.nan)
            # Remove any records flagged with lower quality
            SNOTEL_SWE = SNOTEL_SWE[SNOTEL_SWE['quality_control_level_code'] == '1']

            return SNOTEL_SWE

        except Exception as e:
            print(f"Snotel data fail, {sitecode}")

def CatchmentInfo(lat, lon, basinname):

    #set up Pandas DF for state streamstats

    Streamstats_cols = ['basin', 'basin_lat', 'basin_lon', 'Drainage_area_mi2', 'Mean_Basin_Elev_ft', 'Perc_Forest', 'Perc_Develop',
                     'Perc_Imperv', 'Perc_Herbace', 'Perc_Slop_30', 'Mean_Ann_Precip_in', 'Snotel_ave_elev_ft']

    Catch_Stats = pd.DataFrame(columns = Streamstats_cols)

    ws = streamstats.Watershed(lat=lat, lon=lon)

    print('Retrieving Drainage Area')
    try:
        darea = ws.get_characteristic('DRNAREA')['value']
    except KeyError:
        darea = np.nan
    except ValueError:
        darea = np.nan

    print('Retrieving Mean Catchment Elevation')
    try:
        elev = ws.get_characteristic('ELEV')['value']
    except KeyError:
        elev = np.nan
    except ValueError:
        elev = np.nan

    print('Retrieving Catchment Land Cover Information')
    try:
        forest = ws.get_characteristic('FOREST')['value']
    except KeyError:
        forest = np.nan
    except ValueError:
        forest = np.nan

    try:
        dev_area = ws.get_characteristic('LC11DEV')['value']
    except KeyError:
        dev_area = np.nan
    except ValueError:
        dev_area = np.nan

    try:
        imp_area = ws.get_characteristic('LC11IMP')['value']
    except KeyError:
        imp_area = np.nan
    except ValueError:
        imp_area = np.nan

    try:
        herb_area = ws.get_characteristic('LU92HRBN')['value']
    except KeyError:
        herb_area = np.nan
    except ValueError:
        herb_area = np.nan

    print('Retrieving Catchment Topographic Complexity')
    try:
        perc_slope = ws.get_characteristic('SLOP30_10M')['value']
    except KeyError:
        perc_slope = np.nan
    except ValueError:
        perc_slope = np.nan

    print('Retrieving Catchment Average Precip')
    try:
        precip = ws.get_characteristic('PRECIP')['value']
    except KeyError:
        precip = np.nan
    except ValueError:
        precip = np.nan


    values = [
        basinname,
        lat,
        lon,
        darea, 
        elev,forest, 
        dev_area,
        imp_area, 
        herb_area,
        perc_slope,
        precip,
        0
            ]

    print(values)
    Catchment_Stats = pd.DataFrame(data = values, index = Streamstats_cols).T
    Catchment_Stats.set_index('basin', inplace=True)
    
    return Catchment_Stats