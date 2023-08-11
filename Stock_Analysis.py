import pandas as pd
import requests
import datetime as dt
import yfinance as yf
import holidays
import numpy as np
import streamlit as st
from bs4 import BeautifulSoup
from lxml import etree
from pandas.api.types import is_numeric_dtype
from yahooquery import Ticker
from stocksymbol import StockSymbol
from math import ceil
from selenium import webdriver
from selenium.webdriver import FirefoxOptions
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

def click_analysis():
    st.session_state['click_analysis'] = True

def unclick_analysis():
    st.session_state['click_analysis'] = False
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

@st.cache_data(ttl=dt.timedelta(hours=30*24))
def get_index_list():
    api_key = st.secrets['api_key']
    ss = get_api_symbols(api_key)
    return ss.index_list

@st.cache_data(ttl=dt.timedelta(hours=30*24))
def get_symbol_list(indexid = 'SPX'):
    api_key = st.secrets['api_key']
    ss = get_api_symbols(api_key)
    return ss.get_symbol_list(index=indexid, symbols_only=True)

@st.cache_data(show_spinner = False, ttl=dt.timedelta(hours=24))
def get_annual_info_stock_macrotrends(smb, df_master):
    user_agent = 'Mozilla/5.0 (iPad; CPU OS 12_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
    # ['Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.27 Safari/537.17',
    # 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36', 
    # 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36', 
    # 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36', 
    # 'Mozilla/5.0 (iPhone; CPU iPhone OS 12_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148', 
    # 'Mozilla/5.0 (Linux; Android 11; SM-G960U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.72 Mobile Safari/537.36'] 

    dct_metrics ={
        'EPS':'eps-earnings-per-share-diluted',
        'NetIncome':'net-income',
        'Shares':'shares-outstanding',
        'Assets':'total-assets',
        'Liabilities':'total-liabilities',
        'Equity':'total-share-holder-equity'
        # , 'fiscal_date':'financial-ratios?freq=A'#'income-statement?freq=A'
    }

    df_data_stock_y = pd.DataFrame()
    for k, val in dct_metrics.items():
        # Obtiene link con ticker y nombre de accion de la tabla maestra
        url = df_master.loc[df_master['Ticker']==smb,'link'].iloc[0].replace('stock-price-history',val)
        
        # Truco para evitar bloqueo de scrapers
        url_req = requests.get(url, headers={'User-Agent': user_agent})
        
        try:
            # Procesa tabla anual
            tabla_y = pd.read_html(url_req.text, attrs={'class': 'historical_data_table table'}, match='Annual')[0] #driver.page_source
            tabla_y.columns = ['year',k]
            
            if df_data_stock_y.empty:
                df_data_stock_y = tabla_y
            else:
                df_data_stock_y = pd.merge(left=df_data_stock_y, right = tabla_y, on='year', how='outer')
            
            # Guarda como numero
            if (k != 'Shares') and not(tabla_y.empty):
                df_data_stock_y[k] = pd.to_numeric(df_data_stock_y[k].apply(lambda x: ''.join(x[1:].split(',')) if not pd.isna(x) else '0'))
        except:
            st.write(f'Ocurrió un error descargando información de {smb})')
            continue

        df_data_stock_y['symbol'] = smb
    
    return df_data_stock_y
    
@st.cache_data(show_spinner = False, ttl=dt.timedelta(hours=24))
def get_annual_info_macrotrends(symbols, df_master):
    st.write('_Se está descargando la información de las acciones seleccionadas. Este proceso puede tardar varios minutos._')
    progress_bar = st.progress(0, text='Inicia descarga de información. 0.0%')
    # Se guarda la tabla anual
    df_data_y = pd.DataFrame()
    for n,smb in enumerate(symbols):
        df_data_stock_y = get_annual_info_stock_macrotrends(smb, df_master)   

        # Procesar la ultima fecha fiscal para asociar a cada año
        df_data_stock_y['diff_year'] = df_data_stock_y['year'].diff().expanding().sum()
        if not df_data_stock_y.empty:
            try:
                stock = Ticker(smb)
                lastfiscaldate = dt.datetime.strptime(stock.get_modules('defaultKeyStatistics')[smb]['lastFiscalYearEnd'],'%Y-%m-%d')
                df_data_stock_y.loc[df_data_stock_y['year'] == df_data_stock_y['year'].max(),'lastfiscaldate'] = lastfiscaldate
                df_data_stock_y.loc[df_data_stock_y['year'] != df_data_stock_y['year'].max(),'lastfiscaldate'] = df_data_stock_y.loc[df_data_stock_y['year'] != df_data_stock_y['year'].max(),:].apply(lambda x: dt.datetime(int(lastfiscaldate.year+x['diff_year']),lastfiscaldate.month,lastfiscaldate.day), axis=1)
            except:
                df_data_stock_y.loc[df_data_stock_y['year'] == df_data_stock_y['year'].max(),'lastfiscaldate'] = np.nan
                df_data_stock_y['lastfiscaldate'] = df_data_stock_y['year'].apply(lambda x: dt.date(x,12,31))
                # print(e)
            # Guarda la información en una tabla general
            df_data_y = pd.concat([df_data_y, df_data_stock_y], ignore_index=True)

            progress_bar.progress((n+1)/len(symbols), text=f'Completa información de {smb}. **({(n+1)/len(symbols):,.1%})**')
        else:
            st.write(f'Ocurrió un error. No hay información de {smb}. ({n+1}/{len(symbols)})')
    
    df_data_y['lastfiscaldate'] = pd.to_datetime(df_data_y['lastfiscaldate'])
    df_data_y['date_price'] = df_data_y['lastfiscaldate'].apply(next_business_day)

    return df_data_y

@st.cache_data(ttl=dt.timedelta(hours=1))
def get_data_yahoo(symbols, start_date = dt.date(2009,1,1)):
    df_yahoo = yf.download(symbols,start=start_date)
    df_prices = df_yahoo['Close']
    df_prices = df_prices.reset_index().melt(id_vars='Date',var_name='symbol',value_name='close')
    df_prices['last_close'] = df_prices.sort_values(by='Date').groupby('symbol')['close'].transform('last')
    return df_prices

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
st.write('Este sitio comprende alrededor de ~6000 acciones. A continuación, se puede descargar un archivo con el resumen de todas las acciones disponibles u optar por cargar una versión actualizada.')
st.write('**NOTA:** La descarga de esta información se realiza 1 vez cada 30 días y puede tardar unos minutos.')

opciones = ['WebScraping desde servidor.', 'Subir un archivo propio.', 'Usar última versión.']
opcion = st.radio(
            label = 'Escoja la opción para actualizar las acciones disponibles',
            options = opciones,
            horizontal = True
        )

if opcion == opciones[0]:
    try:
        df_master = get_available_stock( url = 'https://www.macrotrends.net/stocks/stock-screener')
        df_master.to_excel('files/df_master.xlsx')
    except:
        st.error('Ocurrió un error en el proceso de WebScraping. Por favor suba el archivo manualmente.')
        st.info('Para ejecutar el código de WebScraping en su computador siga las instrucciones en la sección "Acciones Disponibles".',icon='🗨️')
        df_master = pd.DataFrame()
elif opcion == opciones[1]:
    # Reading new file
    file_master = st.file_uploader(
        label='Selecciona un archivo para cargar',
        type=['xlsx', 'xlsm', 'xls'],
        accept_multiple_files = False
    )
    if file_master:
        with open(f'files/{file_master.name}',"wb") as fh:
            fh.write(file_master.read())
        df_master = pd.read_excel(f'files/{file_master.name}', index_col=0)
        df_master = pd.read_excel('files/df_master.xlsx', index_col=0)
    else:
        df_master = pd.DataFrame()
else:
    df_master = pd.read_excel('files/df_master.xlsx', index_col=0)

if not df_master.empty:
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
            index = len(sorted(set(df_index['indexName']))),
            on_change=unclick_analysis
        )

    add_stocks = col1.multiselect(
                    label = 'Puede agregar acciones puntuales a la selección. (_opcional_)',
                    options = sorted(set(df_master.loc[df_master['Ticker'].str.contains('https:') == False,'Ticker'])),
                    on_change=unclick_analysis
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

    symbols = [x for x in lst_stocks if x not in lst_not_stocks]
    if len(symbols) > 550:
        st.write('La descarga de información puede tomar tiempo por lo que se sugiere limitar el número de acciones en grupos de 500. Para esto puede hacer uso del slider:')
        slices = st.slider(
                    label = 'slice stocks',
                    label_visibility='hidden',
                    min_value = 1,
                    max_value = len(symbols),
                    value = [1,500]
                )
        st.write('Se procesarán las siguientes acciones:')
        symbols = symbols[slices[0]-1:slices[-1]-1]
        st.write(symbols)
    # endregion

    # region: Descarga de Información
    if 'click_analysis' not in st.session_state:
        st.session_state['click_analysis'] = False

    col1, col2 = st.columns(2)
    with col1:
        st.button('Descarga de Datos :arrow_down_small:', on_click=click_analysis)
        if st.session_state['click_analysis']:
            df_data_y = get_annual_info_macrotrends(symbols, df_master)
        else:
            df_data_y = pd.DataFrame()

    with col2:
        if not df_data_y.empty:
            minyear = df_data_y['date_price'].dt.year.min()
            df_prices = get_data_yahoo(symbols, start_date=dt.date(minyear,1,1))
            df_data_y = pd.merge(left=df_data_y, right=df_prices, how='left', left_on=['date_price','symbol'], right_on=['Date','symbol'])
            # Se eliminan columnas innecesarias
            df_data_y.drop(columns=['diff_year','Date'], inplace=True)
            df_data_y = df_data_y.loc[(df_data_y['Equity']>0)&(df_data_y['Shares']>0),:]
            # Se calculan indicadores
            df_data_y['PE'] = df_data_y['close']/df_data_y['EPS']
            df_data_y['LeverR'] = df_data_y['Assets']/df_data_y['Equity']
            df_data_y['PB'] = df_data_y['close']/((df_data_y['Assets']-df_data_y['Liabilities'])/df_data_y['Shares'])
            df_data_y['ROE'] = df_data_y['NetIncome']/df_data_y['Equity']
            st.download_button(        
                    label=':video_game: Archivo',
                    help='Descargar información anual de acciones.',
                    data=convertir_csv(df_data_y),
                    file_name=f'data_y.csv',
                    mime='text/csv',
                )
        else:
            minyear = 2009
    # endregion

    if not df_data_y.empty:
        # region: Análisis de Acciones
        st.header('Análisis de Acciones :chart_with_upwards_trend:')
        st.write('Se calculan varios indicadores y se estima el precio promedio al que debería estar la acción.')
        st.write('Para esto se debe seleccionar un año a partir del cual promediar los resultados.')
        first_year = st.number_input(
                    label = 'Año Inicial',
                    min_value = minyear,
                    max_value = dt.date.today().year
                )
        dct_agg = {x:'mean' for x in df_data_y.columns if x != 'close' and is_numeric_dtype(df_data_y[x])}
        dct_agg.update({'close':'first','last_close':'first'})
        df_analysis = df_data_y.loc[df_data_y['year']>=first_year,:].groupby('symbol').agg(dct_agg)
        df_analysis['price_obj'] = df_analysis['PE']*df_analysis['EPS']
        df_analysis['price_obj_20'] = df_analysis['price_obj']*0.8
        df_analysis['price_obj_30'] = df_analysis['price_obj']*0.7
        df_analysis['diff'] = (df_analysis['last_close']-df_analysis['price_obj'])/abs(df_analysis['price_obj'])
        df_analysis = pd.merge(left=df_analysis.reset_index(), right=df_master[['Ticker','Stock Name','Industry']], how='left', left_on='symbol', right_on='Ticker')
        df_analysis.sort_values(by='diff',inplace=True)
        df_analysis_show = df_analysis.loc[(df_analysis['EPS']>0)&(df_analysis['PE']<25),['symbol','Stock Name','Industry','EPS','PE','ROE','PB','LeverR','last_close','price_obj','price_obj_20','price_obj_30','diff']]
        st.download_button(        
                    label=':video_game: Archivo Análisis',
                    help='Descargar información de análisis.',
                    data=convertir_csv(df_analysis_show),
                    file_name=f'data_analysis.csv',
                    mime='text/csv',
                )
        st.write('Se filtran las acciones con EPS negativo y PE mayor a 25.')
        st.dataframe(df_analysis_show.set_index('symbol').head(25))

        st.subheader('Proyección de Expertos')
        stock_proy = st.selectbox(
                        label = 'Seleccione una acción para ver su proyección.',
                        options = symbols
                    )
        url_proy = f'https://money.cnn.com/quote/forecast/forecast.html?symb={stock_proy}'
        req_proy = requests.get(url_proy)
        soup = BeautifulSoup(req_proy.content, "html.parser")
        dom = etree.HTML(str(soup))
        st.image('https:'+dom.xpath('//div[@class="wsod_chart"]')[0].find('.//img').get('src'))

        # endregion


    # endregion