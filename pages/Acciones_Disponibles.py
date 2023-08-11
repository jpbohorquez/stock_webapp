import streamlit as st

st.set_page_config(
    page_title="Stock Webapp",
    layout='wide'
)

st.title('Acciones Disponibles :computer:')
st.write('Esta sección presenta el código necesario para descargar todas las acciones disponibles de [macrotrends](https://www.macrotrends.net/stocks/stock-screener).')
st.write('Después de haberlo ejecutado, puede cargarlo en la página principal del análisis de acciones.')

st.code(
    r'''
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.common.exceptions import TimeoutException

url_gen = 'https://www.macrotrends.net/stocks/stock-screener'

# Path of chromedriver
s = Service(r'drivers\chromedriver')

# Creating the driver (headless)
options = Options()  # Initialize an instance of the Options class
options.add_argument("--headless=new")
driver = webdriver.Chrome(service=s, options=options)

# Open website
driver.get(url_gen)

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
lst_records = []
done_pages = 0
while done_pages < total_pages:
    # Procesa información
    filas = tabla.find_elements(By.XPATH, './/div[@role="row"]')
    lst_records += [tuple(f.text.split('\n')) + (f.find_element(By.TAG_NAME,'a').get_attribute('href'),) for f in filas]

    # Actualiza contador y da clic en la siguiente página
    done_pages += 1
    print(f'Procesa página {done_pages} de {total_pages}')
    next_btn.click()

df_master = pd.DataFrame.from_records(lst_records, columns = cols)

# Cierra el navegador
driver.quit()

# Exporta el archivo
df_master.to_excel('df_master.xlsx')
    '''
)