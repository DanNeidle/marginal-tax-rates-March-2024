import pandas as pd
import json

"""
Important notes and limitations

1. the model assumes everybody in the income percentiles receives only employment income; clearly that is incorrect. That should not make much difference as long as this code is not used to model changes in national insurance, only income tax changes

2. The assumption of a uniform wage growth across all percentiles is a simplification.

"""

DATASET_INITIAL = "rUK 2024-25"
DATASET_POLICY_CHANGE = "Reform UK manifesto"

# this uses the ETIs recommended by the Scottish Fiscal Commission. The Scottish figures will be higher than for the rest of the UK
# given the obvious propoensity for Scottish taxpayers to move to England... this therefore likely represents an over-estimate
# https://www.fiscalcommission.scot/publications/how-we-forecast-behavioural-responses-to-income-tax-policy-march-2018/
ELASTICITY_OF_TAXABLE_INCOME = {
                                50000: 0.015,
                                80000: 0.10,
                                150000: 0.20,
                                300000: 0.35,
                                500000: 0.55,
                                1e9: 0.75
                                }

# for testing how sensitive the analysis is to the ETI
ETI_SENSITIVITY_FACTOR = 1.00

# how much we increase the gross income to calculate the marginal rate. Fails to catch weird effects like the marriage allowance, but that's of limited relevance
GROSS_INCOME_PERTUBATION = 1000


# source for the percentile data: https://www.gov.uk/government/statistics/percentile-points-from-1-to-99-for-total-income-before-and-after-tax
PRE_TAX_INCOME_PERCENTILE_DATA = "pre_tax_income_percentiles.xlsx"

# this is used to uprate each income percentile to its level for 2025/26 (or whichever year is to be modeled)
# OBR says % of taxpayers in higher and additional rates for 25/26 is (6.1 + 1.2) / 37.8 = 21%.  https://obr.uk/efo/economic-and-fiscal-outlook-march-2024/
# that implies income growth in each percentile of 1.16
WAGE_GROWTH_SINCE_2020_21 = 1.16

# number of taxpayers for 2025/26 from row 9 table 3.7 here https://obr.uk/efo/economic-and-fiscal-outlook-march-2024/
POPULATION_OF_TAXPAYERS = 37800000


DATASET_FILENAME = "UK_marginal_tax_datasets.json"

def load_data_from_json():
        try:
            with open(DATASET_FILENAME, 'r') as f:
                data = json.load(f)
                return data
        except Exception as e:
            print("Tax rate data not found")
            exit()
            
def find_elasticity_for_income_level(gross_income):
    for income_threshold in sorted(ELASTICITY_OF_TAXABLE_INCOME.keys()):
        if gross_income <= income_threshold:
            return ETI_SENSITIVITY_FACTOR * ELASTICITY_OF_TAXABLE_INCOME[income_threshold]
    # Fallback in case all thresholds are lower than gross_income
    return ETI_SENSITIVITY_FACTOR * ELASTICITY_OF_TAXABLE_INCOME[max(ELASTICITY_OF_TAXABLE_INCOME.keys())]

# Unified function to calculate tax and NI
def calculate_tax_and_ni(gross_income, relevant_dataset, tax_type):
    
    relevant_data = tax_data[relevant_dataset]
    total_tax = 0
    
    # tweaks for income tax
    if tax_type == "income tax":
        
        
        # deal with personal allowance taper and marriage allowance
        if gross_income > relevant_data["allowance withdrawal threshold"]:
            modified_personal_allowance = max(0, relevant_data["statutory personal allowance"] - relevant_data["allowance withdrawal rate"] * (gross_income - relevant_data["allowance withdrawal threshold"]))
        
        else:
            modified_personal_allowance = relevant_data["statutory personal allowance"]
            
        taxable_net_income = max(0, gross_income - modified_personal_allowance)

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


def return_total_tax(gross_income, dataset):
    income_tax = calculate_tax_and_ni(gross_income, dataset, "income tax")
    ni = calculate_tax_and_ni(gross_income, dataset, "NI")
    return income_tax + ni

def friendly_number(n):
    suffixes = {1: 'st', 2: 'nd', 3: 'rd'}
    if 10 <= n % 100 <= 20:
        suffix = 'th'
    else:
        suffix = suffixes.get(n % 10, 'th')
    return f"{n}{suffix}"

"""
methodology here:
1. work out current tax position of taxpayer and marginal rate
2. work out new tax position of taxpayer and new marginal rate
3. increase their pre-tax income by (% increase in marginal rate) x ETI for that level of income
4. calculate final tax position in light of increased taxable income
"""  

def calculate_effect_of_change():

    # Create a range of gross incomes
    # Load the percentiles
    df = pd.read_excel(PRE_TAX_INCOME_PERCENTILE_DATA)

    data = []    
    total_static_tax_after_policy_change = 0
    total_dynamic_tax_after_policy_change = 0

    # Iterate through the percentiles and calculate tax for each row
    for index, row in df.iterrows():
        percentile = row.iloc[0]
        gross_income = row.iloc[1] * WAGE_GROWTH_SINCE_2020_21
        
        total_tax_initial = return_total_tax(gross_income, DATASET_INITIAL)
        total_tax_initial_plus_pertubation = return_total_tax(gross_income + GROSS_INCOME_PERTUBATION, DATASET_INITIAL)
        marginal_rate_initial = (total_tax_initial_plus_pertubation - total_tax_initial) / GROSS_INCOME_PERTUBATION
        retention_rate_initial = 1 - marginal_rate_initial
        
        total_tax_after_policy_change = return_total_tax(gross_income, DATASET_POLICY_CHANGE)
        total_tax_after_policy_change_plus_pertubation = return_total_tax(gross_income + GROSS_INCOME_PERTUBATION, DATASET_POLICY_CHANGE)
        marginal_rate_after_policy_change = (total_tax_after_policy_change_plus_pertubation - total_tax_after_policy_change) / GROSS_INCOME_PERTUBATION
        retention_rate_after_policy_change = 1 - marginal_rate_after_policy_change
        
        percentage_change_in_marginal_retention_rate = (retention_rate_after_policy_change - retention_rate_initial) / retention_rate_initial
        percentage_change_in_taxable_income = percentage_change_in_marginal_retention_rate * find_elasticity_for_income_level(gross_income)
        
        dynamic_gross_income = gross_income * (1 + percentage_change_in_taxable_income)
        dynamic_tax_after_policy_change = return_total_tax(dynamic_gross_income, DATASET_POLICY_CHANGE)
        
        
        dynamic_tax_change = dynamic_tax_after_policy_change - total_tax_initial
        total_static_tax_after_policy_change += (total_tax_after_policy_change - total_tax_initial) * POPULATION_OF_TAXPAYERS / 100 / 1e9
        total_dynamic_tax_after_policy_change += dynamic_tax_change * POPULATION_OF_TAXPAYERS / 100 / 1e9
        
        # net_income = gross_income - total_tax_ni
        row = {
            'Percentile': friendly_number(percentile),
            'Gross Income': f"£{gross_income:,.0f}",
            'Current Tax': f"£{total_tax_initial:,.0f}",
            'Marginal Rate': f"{100 * marginal_rate_initial:.1f}%",
            'New tax (static)': f"£{total_tax_after_policy_change:,.0f}",
            'New marginal rate': f"{100*marginal_rate_after_policy_change:,.1f}%",
            'Delta marginal rate': f"{100*(marginal_rate_after_policy_change - marginal_rate_initial):,.1f}%",
            'Dynamic gross income': f"£{dynamic_gross_income:,.0f}",
            'New tax (Dynamic)': f"£{dynamic_tax_after_policy_change:,.0f}",
            'DYNAMIC TAX CHANGE': f"£{dynamic_tax_change:,.0f}"
        }
        data.append(row)
    
        # print(f"{friendly_number(percentile)}: gross income £{gross_income:,.0f}, current tax £{total_tax_initial:,.0f} and marginal rate {100*marginal_rate_initial:.1f}% to £{total_tax_after_policy_change:,.0f} - marginal rate reduction {100 * percentage_reduction_in_marginal_rate:.1f}. Dynamic effects increase income {percentage_increase_in_taxable_income} and dynamic tax {dynamic_tax_after_policy_change:,.0f}")
        
        
        
    results_dataframe = pd.DataFrame(data)
    # results_dataframe.set_option('display.max_rows', len(df))

    print(results_dataframe.to_string(index=False))
        

    return total_static_tax_after_policy_change, total_dynamic_tax_after_policy_change


if __name__ == '__main__':

    tax_data = load_data_from_json()

    static_change, dynamic_change = calculate_effect_of_change()
    print(f"\nCalculated impact of '{DATASET_POLICY_CHANGE}' compared to '{DATASET_INITIAL}':")
    print(f"Static estimate: £{static_change:,.0f}bn")
    print(f"Dynamic estimate: £{dynamic_change:,.0f}bn")
    
