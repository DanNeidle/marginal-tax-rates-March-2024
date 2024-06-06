import pandas as pd
import numpy as np
import plotly.graph_objects as go
from PIL import Image
import json

# if set to [] then charts everything, or can be e.g. ["rUK 2023-24", "rUK 2024-25"] 
DATA_TO_CHART = []

# Whether to export to Excel
EXPORT_TO_EXCEL = False
EXCEL_FILE = 'UK_marginal_tax_rates.xlsx'
DEFAULT_DATASET = "rUK 2024-25"

INCLUDE_STUDENT_LOAN = True
STUDENT_LOAN_RATE = 0.09
STUDENT_LOAN_THRESHOLD = 27295 # this is plan two, started course between 1 September 2012 and 31 July 2023 

INCLUDE_CHILD_BENEFIT = True
CHILDREN = 3

INCLUDE_CHILDCARE = False  # note if childcare subsidies are modelled it swamps all other marginal rate effects.
INCLUDE_MARRIAGE_ALLOWANCE = False   # also swamps all other marginal rate effects
PLOT_GROSS_VS_NET = True   # highly recommended if showing childcare subsidy or marriage allowance

# Constants
RESOLUTION = 100        # the amount by which gross salary is incremented
MAX_INCOME = 180000  

DATASET_FILENAME = "UK_marginal_tax_datasets.json"
LOGO_FILE = "logo_full_white_on_blue.jpg"

def load_data_from_json():
        try:
            with open(DATASET_FILENAME, 'r') as f:
                data = json.load(f)
                return data
        except Exception as e:
            print("Tax rate data not found")
            exit()
            
def load_logo():
    
    logo_jpg = Image.open(LOGO_FILE)
    return [dict(
            source=logo_jpg,
            xref="paper", yref="paper",
            x=1, y=1.01,
            sizex=0.1, sizey=0.1,
            xanchor="right", yanchor="bottom"
        )]
    
def export_to_excel(dataframes):
    with pd.ExcelWriter(EXCEL_FILE) as writer:
        for name, df in dataframes.items():
            df.to_excel(writer, sheet_name=name)
        
    print(f"Written to Excel {EXCEL_FILE}")
    

# Unified function to calculate tax and NI
def calculate_tax_and_ni(gross_income, country_and_year, tax_type, do_child_benefit, do_student_loan):
    
    relevant_data = tax_data[country_and_year]
    total_tax = 0
    
    # tweaks for income tax
    if tax_type == "income tax":
        
        # deal with personal allowance taper and marriage allowance
        if gross_income > relevant_data["allowance withdrawal threshold"]:
            modified_personal_allowance = max(0, relevant_data["statutory personal allowance"] - relevant_data["allowance withdrawal rate"] * (gross_income - relevant_data["allowance withdrawal threshold"]))
        
        elif INCLUDE_MARRIAGE_ALLOWANCE and gross_income < relevant_data["marriage allowance max earnings"]:
            modified_personal_allowance = relevant_data["statutory personal allowance"] * (1 + relevant_data["marriage allowance"])
        else:
            modified_personal_allowance = relevant_data["statutory personal allowance"]
            
        taxable_net_income = max(0, gross_income - modified_personal_allowance)
        
        # give child benefit (modelled as a negative tax, not technically correct but gives right result)
        if do_child_benefit and CHILDREN > 0:
            total_child_benefit = 52 * (relevant_data["child benefit"]["1st"] + relevant_data["child benefit"]["subsequent"] * (CHILDREN - 1))
            if gross_income < relevant_data["HICBC start"]:
                total_tax -= total_child_benefit
            elif gross_income > relevant_data["HICBC end"]:
                total_tax -= 0
            else:
                child_benefit_reduction = (gross_income - relevant_data["HICBC start"]) / (relevant_data["HICBC end"] - relevant_data["HICBC start"])
                total_tax -= total_child_benefit * (1 - child_benefit_reduction)
                
        # give childcare subsidy (modelled as a negative tax, not technically correct but gives right result)
        if INCLUDE_CHILDCARE and CHILDREN > 0:
            if relevant_data["childcare min earnings"] < gross_income < relevant_data["childcare max earnings"]:
                total_tax -= relevant_data["childcare subsidy per child"] * min(CHILDREN, relevant_data["childcare max children"])
                
        # simple student loan modelling - modelled as income tax, not technically correct but economically it is a tax
        if do_student_loan and gross_income > STUDENT_LOAN_THRESHOLD:
            total_tax += (gross_income - STUDENT_LOAN_THRESHOLD) * STUDENT_LOAN_RATE

    else:
        
        taxable_net_income = gross_income
            
    
    
    last_threshold = 0
    
    for band in relevant_data[tax_type]:
        if "threshold" not in band:
            band["threshold"] = 1e12   # easier if we artificially give the highest band a limit
            
        gross_income_in_band = min(taxable_net_income, band["threshold"]) - last_threshold
        tax_in_band = gross_income_in_band * band["rate"]
        total_tax += tax_in_band
            
        last_threshold = band["threshold"]
        
        if taxable_net_income <= band["threshold"]:
            break
            
    return total_tax

def calculate_tax(dataset, do_child_benefit, do_student_loan):

    # Create a range of gross incomes
    gross_incomes = np.arange(0, MAX_INCOME + RESOLUTION, RESOLUTION)

    # Calculate net income and marginal rate
    data = []
    for i in range(len(gross_incomes)):
        gross_income = gross_incomes[i]
        income_tax = calculate_tax_and_ni(gross_income, dataset, "income tax", do_child_benefit, do_student_loan)
        employee_ni = calculate_tax_and_ni(gross_income, dataset, "NI", None, None)
        total_tax_ni = income_tax + employee_ni
        net_income = gross_income - total_tax_ni
        marginal_rate = 0 if i == 0 else (total_tax_ni - data[i-1][3]) / RESOLUTION
        data.append([gross_income, income_tax, employee_ni, total_tax_ni, net_income, marginal_rate])

    # Create DataFrame
    return pd.DataFrame(data, columns=["gross income", "income tax", "employee NI", "total tax/NI", "net income", "marginal rate"])


if __name__ == '__main__':

    tax_data = load_data_from_json()
    logo_layout = load_logo()

    # if we are charting all datasets then populate list
    if DATA_TO_CHART == []:
        DATA_TO_CHART = list(tax_data.keys())

    # this is where we save the dataframes for excel export
    created_data = {}

    # Plot of Gross Income vs. Marginal Rate
    fig_marginal_rate = go.Figure()

    for dataset in DATA_TO_CHART:
        
        df = calculate_tax(dataset, False, False)
        created_data[f"{dataset}"] = df
        fig_marginal_rate.add_trace(go.Scatter(x=df['gross income'], y=df['marginal rate']*100, mode='lines', name=dataset, visible=True if dataset == DEFAULT_DATASET else 'legendonly'))
        
        if INCLUDE_CHILD_BENEFIT:
            df = calculate_tax(dataset, True, False)
            created_data[f"{dataset} CB"] = df
            fig_marginal_rate.add_trace(go.Scatter(x=df['gross income'], y=df['marginal rate']*100, mode='lines', name=dataset + " w/ child benefit", visible='legendonly'))
            
        if INCLUDE_STUDENT_LOAN: 
            df = calculate_tax(dataset, True, True)
            created_data[f"{dataset} CB SL"] = df
            fig_marginal_rate.add_trace(go.Scatter(x=df['gross income'], y=df['marginal rate']*100, mode='lines', name=dataset + " w/ child benefit and student loans", visible='legendonly'))


    title = "Gross employment income vs marginal tax rate"   
    if INCLUDE_CHILDCARE:
        title += ", inc childcare subsidy"

    fig_marginal_rate.update_layout(
                    title=title,
                    title_font=dict(size=32),
                    xaxis_title='Gross employment income (£)',
                    xaxis_title_font=dict(size=18),
                    yaxis_title='Marginal tax rate (%)',
                    yaxis_title_font=dict(size=18), 
                    hovermode='x',
                    images=logo_layout,
                    legend=dict(orientation="h", yanchor="top", y=-0.075, xanchor="center", x=0.5, bordercolor="Black", borderwidth=1)
                    )
    
    # if we're not modelling marriage allowance or childcare then set y axis limit to 90%
    # otherwise will autoscale and so capture crazy high marginal rates
    if (not INCLUDE_MARRIAGE_ALLOWANCE) and (not INCLUDE_CHILDCARE):
        fig_marginal_rate.update_yaxes(range=[0, 90])
        
    fig_marginal_rate.update_xaxes(tickprefix="£")
    fig_marginal_rate.update_yaxes(ticksuffix="%")

    fig_marginal_rate.show()


    if PLOT_GROSS_VS_NET:
        # Plot of Gross Income vs. Net Income
        fig_net_income = go.Figure()

        for dataset in DATA_TO_CHART:
            df = calculate_tax(dataset, False, False)
            created_data[f"{dataset} gross v net"] = df
            
            fig_net_income.add_trace(go.Scatter(x=df['gross income'], y=df['net income'], mode='lines', name=dataset,  hovertemplate='£%{y:,.0f}', visible=True if dataset == DEFAULT_DATASET else 'legendonly'))
            
            if INCLUDE_CHILD_BENEFIT:
                df = calculate_tax(dataset, True, False)
                created_data[f"{dataset} gross v net"] = df
                fig_net_income.add_trace(go.Scatter(x=df['gross income'], y=df['net income'], mode='lines', name=dataset + " w/ child benefit",  hovertemplate='£%{y:,.0f}', visible='legendonly'))
                
            if INCLUDE_STUDENT_LOAN: 
                df = calculate_tax(dataset, True, True)
                created_data[f"{dataset} gross v net"] = df
                fig_net_income.add_trace(go.Scatter(x=df['gross income'], y=df['net income'], mode='lines', name=dataset + " w/ child benefit and student loans",  hovertemplate='£%{y:,.0f}', visible='legendonly'))
            
            title = 'Gross employment income vs net income'
            if INCLUDE_CHILDCARE:
                title += ", inc childcare subsidy"
                

        fig_net_income.update_layout(
                        title=title,
                        title_font=dict(size=32),
                        xaxis_title='Gross employment income (£)',
                        xaxis_title_font=dict(size=18),
                        yaxis_title='Net income (£)',
                        yaxis_title_font=dict(size=18), 
                        hovermode='x',
                        images=logo_layout,
                        legend=dict(orientation="h", yanchor="top", y=-0.075, xanchor="center", x=0.5, bordercolor="Black", borderwidth=1)
                    )
        
        fig_net_income.update_xaxes(tickprefix="£")
        fig_net_income.update_yaxes(tickprefix="£")
        
        fig_net_income.show()
        
    if EXPORT_TO_EXCEL:
        export_to_excel(created_data)
        