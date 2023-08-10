import streamlit as st
import os, sys

@st.cache_resource
def installff():
  os.system('sbase install geckodriver')
  os.system('ln -s /home/appuser/venv/lib/python3.8/site-packages/selenium/webdriver/geckodriver /home/appuser/venv/bin/geckodriver')

_ = installff()
from selenium import webdriver
from selenium.webdriver import FirefoxOptions


import pandas as pd
import requests
import datetime as dt
import yfinance as yf
import holidays
import numpy as np
# import streamlit as st
from pandas.api.types import is_numeric_dtype
from yahooquery import Ticker
from stocksymbol import StockSymbol
from math import ceil
# from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

st.set_page_config(
    page_title="Stock Webapp",
    layout='wide'
)

# region: Funciones auxiliares
def next_business_day(date = dt.date.today(), country = 'US', market='NYSE'):
    '''
        Devuelve el siguiente día hábil, considerando festivos según el país o mercado financiero.
        Usa librería holidays: https://python-holidays.readthedocs.io/en/latest/
    '''
    if market:
        festivos = holidays.financial_holidays(market)
    elif country:
        festivos = holidays.country_holidays(country)
    else:
        festivos = holidays.country_holidays('US')
    
    while((date in festivos) or (date.weekday() in [5,6])):
        date = date + dt.timedelta(days=1)
    
    return date
# endregion

# region: Funciones para conexión de datos
def val_driver(driver):  # Si retorna falso se descarta el cache.
    try:
        driver.window_handles
        rta = True
    except:
        rta = False
    return rta

@st.cache_resource(validate=val_driver)
def get_driver():
    opts = FirefoxOptions()
    opts.add_argument("--headless")
    return webdriver.Firefox(options=opts)
    # options = Options()
    # options.add_argument('--disable-gpu')
    # options.add_argument("--headless=new")
    # return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

@st.cache_data
def get_api_symbols(api_key):
    return StockSymbol(api_key)
# endregion

# region: Funciones de descarga de información
@st.cache_data(ttl=dt.timedelta(hours=30*24))
def get_available_stock( url = 'https://www.macrotrends.net/stocks/stock-screener'):    
    driver = get_driver()
    # Open website
    driver.get(url)

    # Detiene ejecución hasta que aparezca la tabla
    WebDriverWait(driver, 15).until(ec.presence_of_element_located((By.XPATH, '//div[@id="jqxGrid"]')))

    # Pager es la barra de abajo que tiene el numero de paginas y los botones de cambio de pagina
    pager = driver.find_element(By.XPATH, '//div[@id="pagerjqxGrid"]')

    total_stocks = int(pager.text.split(' of ')[-1])
    stocks_per_page = int(pager.text.split(' of ')[0].split('-')[-1])
    total_pages = ceil(total_stocks/stocks_per_page)

    # Botón de cambio de pagina
    next_btn = pager.find_element(By.XPATH, './/div[(@type="button") and (@title="next")]')

    # Tabla
    tabla = driver.find_element(By.XPATH, '//div[@id="jqxGrid"]')
    cols = [c.text.split('\n')[0] for c in tabla.find_elements(By.XPATH, './/div[@role="columnheader"]')]+['link']

    # Se llena la tabla maestra
    progress_text = '_Se está descargando la información de las acciones disponibles. Este proceso puede tardar varios minutos._'
    progress_bar = st.progress(0, text=progress_text)
    lst_records = []
    done_pages = 0
    while done_pages < total_pages:
        # Procesa información
        filas = tabla.find_elements(By.XPATH, './/div[@role="row"]')
        lst_records += [tuple(f.text.split('\n')) + (f.find_element(By.TAG_NAME,'a').get_attribute('href'),) for f in filas]

        # Actualiza contador y da clic en la siguiente página
        done_pages += 1
        # print(f'Procesa página {done_pages} de {total_pages}')
        progress_bar.progress(done_pages/total_pages, text=progress_text+f' **({done_pages/total_pages:,.1%})**')
        next_btn.click()
    
    # driver.quit()

    df_master = pd.DataFrame.from_records(lst_records, columns = cols)

    for ind,row in df_master.loc[pd.isna(df_master['link']),:].iterrows():
        for col in row.index:
            if 'https:' in str(row[col]):
                df_master.loc[ind,'link'] = row[col]

    return df_master

@st.cache_data
def get_index_list():
    api_key = st.secrets['api_key']
    ss = get_api_symbols(api_key)
    return ss.index_list

@st.cache_data
def get_symbol_list(indexid = 'SPX'):
    api_key = st.secrets['api_key']
    ss = get_api_symbols(api_key)
    return ss.get_symbol_list(index=indexid, symbols_only=True)

@st.cache_data
def convertir_csv(df):
    return df.to_csv().encode('utf-8')
    
# endregion

# region: Layout principal
st.title('Análisis de Acciones :money_with_wings:')
st.write('Con este aplicativo web es posible realizar un análisis financiero de un grupo de acciones específicas.')
st.write('Las acciones pueden ser parte de un índice particular o se pueden seleccionar puntualmente.')

# region: Acciones Disponibles
st.header('Acciones Disponibles :scroll:')
st.write('La fuente principal de información es el sitio web [macrotrends](https://www.macrotrends.net/stocks/stock-screener).')
st.write('Este sitio comprende alrededor de ~6000 acciones. A continuación, se puede descargar un archivo con el resumen de todas las acciones disponibles.')
st.write('**NOTA:** La descarga de esta información se realiza 1 vez cada 30 días y puede tardar unos minutos.')

# TODO: probar en try y catch y si falla subir archivo
# TODO: crear página que muestre codigo para descargar el df_master
# TODO: probar web scraping mediante firefox y no chrome
df_master = get_available_stock( url = 'https://www.macrotrends.net/stocks/stock-screener')
# driver.quit()
st.download_button(
            label='Descargar Info Acciones :arrow_down_small:',
            help='Descargar información de acciones disponibles.',
            data=convertir_csv(df_master),
            file_name=f'available_stock.csv',
            mime='text/csv',
        )
# endregion

# region: Selección de Acciones
index_list = get_index_list()
df_index = pd.DataFrame.from_records(index_list)

st.header('Selección de Acciones :bookmark:')
col1, col2 = st.columns(2)
indice = col1.selectbox(
        label = 'Seleccione un índice que desee analizar. (_opcional_)',
        options = sorted(set(df_index['indexName']))+['No Index'],
        index = len(sorted(set(df_index['indexName'])))
    )

add_stocks = col2.multiselect(
                label = 'Puede agregar acciones puntuales a la selección. (_opcional_)',
                options = sorted(set(df_master.loc[df_master['Ticker'].str.contains('https:') == False,'Ticker']))
            )

if indice == 'No Index':
    lst_stocks = []
else:
    indexid = df_index.loc[df_index['indexName'] == indice,'indexId'].values[0]

    lst_stocks = get_symbol_list(indexid)

lst_stocks += add_stocks
set_aux = set()
lst_stocks = [x for x in lst_stocks if not(x in set_aux or set_aux.add(x))]
lst_not_stocks = [x for x in lst_stocks if x not in df_master['Ticker'].tolist()]

col1.write('Se presenta la lista de acciones de interés:')
col1.write(lst_stocks)

col2.write('Las siguientes acciones no están disponibles en macrotrends:')
col2.write(lst_not_stocks)
# endregion
# endregion