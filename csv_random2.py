import csv
import datetime
import random
import holidays # pip install holidays
import os

def parse_anchor_data(data_str):
    """Parses the string input of anchor data into a dictionary."""
    parsed = {}
    for line in data_str.strip().split('\n'):
        date_str, value_str = line.split('\t')
        # Ensure date parts are zero-padded for consistent parsing
        parts = date_str.split('.')
        formatted_date_str = f"{parts[0]}.{parts[1].zfill(2)}.{parts[2].zfill(2)}"
        parsed[datetime.datetime.strptime(formatted_date_str, '%Y.%m.%d').date()] = float(value_str)
    return dict(sorted(parsed.items()))

def generate_financial_data(start_date_overall, end_date_overall, anchor_data_str, output_dir):
    """
    Generates financial data CSV based on anchor points, holidays, and fluctuation rules.
    """
    anchor_data = parse_anchor_data(anchor_data_str)
    us_holidays = holidays.US()
    
    all_generated_data = [] # To store (date, value) tuples

    # Ensure the overall start date is present, if not, find the earliest anchor
    # and fill flat data until then if needed.
    # For this problem, the first anchor IS the start_date_overall.
    
    current_date = start_date_overall
    
    # Sort anchor dates to process chronologically
    sorted_anchor_dates = sorted(anchor_data.keys())

    # Initial value is from the first anchor
    # Ensure the first day's value is set if it's a business day
    last_value = anchor_data[sorted_anchor_dates[0]]
    if current_date == sorted_anchor_dates[0]:
         if not (current_date.weekday() >= 5 or current_date in us_holidays):
            all_generated_data.append((current_date, last_value))
            # print(f"Anchor Start: {current_date.strftime('%Y.%m.%d')}\t{last_value:.2f}")

    # Iterate through periods defined by anchor points
    for i in range(len(sorted_anchor_dates)):
        period_start_date = sorted_anchor_dates[i]
        val_start_period = anchor_data[period_start_date]

        # Determine the end of the current period and its target value
        if i + 1 < len(sorted_anchor_dates):
            next_anchor_date = sorted_anchor_dates[i+1]
            val_next_anchor = anchor_data[next_anchor_date]
        else:
            # This is the last anchor period, extends to end_date_overall
            next_anchor_date = end_date_overall + datetime.timedelta(days=1) # Target beyond the generation period
            # For the last period, let's assume a neutral trend or extrapolate slightly
            # For simplicity, we'll aim for a relatively flat trend unless specified otherwise
            # Or, use the trend from the previous year if available
            if len(sorted_anchor_dates) > 1:
                prev_anchor_date = sorted_anchor_dates[i-1]
                prev_anchor_val = anchor_data[prev_anchor_date]
                if val_start_period > prev_anchor_val and prev_anchor_val > 0:
                     # If previous year was growth, assume slight growth
                    val_next_anchor = val_start_period * 1.02 # modest 2% growth for the year
                elif val_start_period < prev_anchor_val:
                    # If previous year was decline, assume slight decline
                    val_next_anchor = val_start_period * 0.98
                else:
                    val_next_anchor = val_start_period # Flat
            else:
                val_next_anchor = val_start_period # Flat if only one anchor

        # List of business days in the current period
        # The period is from period_start_date up to (but not including) next_anchor_date
        business_days_in_period = []
        iter_date = period_start_date
        
        # The first day of the period might already be added if it's the overall start
        # We need to ensure values are generated for days *after* period_start_date
        # up to the day *before* next_anchor_date.
        
        # If period_start_date is a business day and is the first day of processing,
        # its value is already set.
        # We need to start generating from the *next* business day.
        
        temp_current_day_for_listing = period_start_date
        while temp_current_day_for_listing < next_anchor_date and temp_current_day_for_listing <= end_date_overall:
            if not (temp_current_day_for_listing.weekday() >= 5 or temp_current_day_for_listing in us_holidays):
                # Only add if it's not the very first anchor day itself (which is handled by val_start_period)
                # unless it's the only day in a "flat" period.
                business_days_in_period.append(temp_current_day_for_listing)
            temp_current_day_for_listing += datetime.timedelta(days=1)

        # Remove the first day if it's the anchor day itself, as its value is already fixed
        # and `last_value` is initialized with it.
        # We generate values for the days *following* the anchor day.
        if business_days_in_period and business_days_in_period[0] == period_start_date:
            # If the first business day is the anchor day, its value is fixed.
            # We will process from the *next* business day in the loop below.
            # `last_value` is already `val_start_period`.
            # Add it to results if not already added (e.g. if it's not the very first day overall)
            is_already_added = any(d[0] == period_start_date for d in all_generated_data)
            if not is_already_added:
                 all_generated_data.append((period_start_date, val_start_period))
                 # print(f"Anchor Period Start: {period_start_date.strftime('%Y.%m.%d')}\t{val_start_period:.2f}")

            business_days_to_process = business_days_in_period[1:]
        else:
            business_days_to_process = business_days_in_period


        # If start and end values for the period are the same (e.g. 2015-2016)
        if val_start_period == val_next_anchor and next_anchor_date.year == period_start_date.year + 1 : # Check if it's a full year of same value
            # print(f"Flat period: {period_start_date.year}")
            for day_in_flat_period in business_days_to_process:
                if day_in_flat_period <= end_date_overall:
                    is_already_added = any(d[0] == day_in_flat_period for d in all_generated_data)
                    if not is_already_added:
                        all_generated_data.append((day_in_flat_period, val_start_period))
                        # print(f"Flat Day: {day_in_flat_period.strftime('%Y.%m.%d')}\t{val_start_period:.2f}")
                    last_value = val_start_period # Update last_value
            current_date = next_anchor_date # Move to the start of the next period
            if next_anchor_date <= end_date_overall and not (next_anchor_date.weekday() >=5 or next_anchor_date in us_holidays):
                is_already_added = any(d[0] == next_anchor_date for d in all_generated_data)
                if not is_already_added:
                    all_generated_data.append((next_anchor_date, val_next_anchor)) # Value for the anchor day itself
                    # print(f"Anchor (End of Flat): {next_anchor_date.strftime('%Y.%m.%d')}\t{val_next_anchor:.2f}")
                last_value = val_next_anchor

            continue # Move to the next anchor period

        # Fluctuating period
        num_days_to_target = len(business_days_to_process)
        if next_anchor_date <= end_date_overall and not (next_anchor_date.weekday() >=5 or next_anchor_date in us_holidays):
             # If the next anchor date itself is a business day and within range,
             # we need to generate values up to the day *before* it.
             # The value for next_anchor_date itself will be val_next_anchor.
             pass # num_days_to_target is correct as it excludes next_anchor_date

        # Counter-trend variables
        counter_trend_days_remaining = 0
        counter_trend_type = None # 'positive_bias' or 'negative_bias'
        overall_trend_is_up = val_next_anchor > val_start_period
        
        # Determine how many counter-trend episodes per year (approx)
        # An episode lasts 5-15 business days. A year has ~252 business days.
        # Let's say 2-4 episodes per year.
        num_counter_trend_episodes = random.randint(2,4) if num_days_to_target > 60 else random.randint(0,1) # Fewer for shorter periods
        
        # Distribute these episodes somewhat evenly, or randomly
        counter_trend_trigger_days = sorted(random.sample(range(num_days_to_target), min(num_counter_trend_episodes, num_days_to_target)))
        trigger_idx = 0

        current_processing_val = last_value # Start with the value from the anchor or previous day

        for day_idx, day_to_process in enumerate(business_days_to_process):
            if day_to_process > end_date_overall:
                break
            
            # --- Counter-Trend Logic ---
            if counter_trend_days_remaining > 0:
                counter_trend_days_remaining -= 1
            elif trigger_idx < len(counter_trend_trigger_days) and day_idx == counter_trend_trigger_days[trigger_idx]:
                counter_trend_days_remaining = random.randint(5, 15) # Duration of counter-trend
                if overall_trend_is_up: # If year is generally UP, force a DOWN period
                    counter_trend_type = 'negative_bias'
                else: # If year is generally DOWN, force an UP period
                    counter_trend_type = 'positive_bias'
                trigger_idx += 1
            else:
                counter_trend_type = None

            # --- Fluctuation Logic ---
            # Calculate remaining business days to the next anchor
            # This counts business days from *tomorrow* up to the day *before* next_anchor_date
            # Or, if next_anchor_date is a business day, up to next_anchor_date itself.
            
            # Simpler: number of steps remaining in business_days_to_process
            steps_remaining_in_period = num_days_to_target - day_idx
            
            target_val_for_next_anchor = val_next_anchor
            if period_start_date == sorted_anchor_dates[-1]: # If this is the last anchor period
                 # For the final stretch to end_date_overall, aim for the extrapolated val_next_anchor
                 # The number of steps is until end_date_overall
                 actual_end_date_for_calc = end_date_overall
                 _temp_days_list = []
                 _d = day_to_process + datetime.timedelta(days=1)
                 while _d <= actual_end_date_for_calc:
                     if not (_d.weekday() >= 5 or _d in us_holidays):
                         _temp_days_list.append(_d)
                     _d += datetime.timedelta(days=1)
                 steps_remaining_in_period = len(_temp_days_list) + 1 # +1 for current step
                 if not _temp_days_list: # If current day is the last business day
                     steps_remaining_in_period = 1


            if steps_remaining_in_period > 0 and current_processing_val > 0:
                # Ideal factor to reach target_val_for_next_anchor from current_processing_val in steps_remaining_in_period
                ideal_daily_geometric_factor = (target_val_for_next_anchor / current_processing_val)**(1 / steps_remaining_in_period)
            elif current_processing_val == target_val_for_next_anchor : # Already at target or steps are zero
                ideal_daily_geometric_factor = 1.0
            elif current_processing_val <= 0 and target_val_for_next_anchor > 0: # Edge case: recovery from zero/negative
                ideal_daily_geometric_factor = 1.05 # try to increase
            elif current_processing_val > 0 and target_val_for_next_anchor <=0:
                ideal_daily_geometric_factor = 0.95 # try to decrease
            else: # Both zero or negative, or other edge cases
                ideal_daily_geometric_factor = 1.0


            # Base percentage change guided by the ideal factor
            target_daily_perc_change = (ideal_daily_geometric_factor - 1) * 100

            # Random fluctuation component
            rand_chance = random.random()
            random_fluctuation_perc = 0

            if counter_trend_type == 'negative_bias': # Force negative/smaller fluctuation
                if rand_chance < 0.7: # 70% small negative
                    random_fluctuation_perc = random.uniform(-1, 0)
                else: # 30% larger negative
                    random_fluctuation_perc = random.uniform(-5, -1) # Bias large ones to be less extreme during counter
            elif counter_trend_type == 'positive_bias': # Force positive/larger fluctuation
                if rand_chance < 0.7: # 70% small positive
                    random_fluctuation_perc = random.uniform(0, 1)
                else: # 30% larger positive
                    random_fluctuation_perc = random.uniform(1, 5)
            else: # Normal fluctuation
                if rand_chance < 0.7: # 70% of days, change is within +/-1%
                    random_fluctuation_perc = random.uniform(-1, 1)
                else: # 30% of days, change is between +/-2% and +/-10%
                    if random.random() < 0.5: # 50/50 positive or negative large change
                        random_fluctuation_perc = random.uniform(2, 10)
                    else:
                        random_fluctuation_perc = random.uniform(-10, -2)
            
            # Combine target-guided change with random fluctuation
            # The random fluctuation should be additive to the target change,
            # but let's make it so the target is a soft guide and randomness still plays a big role.
            # A simple way: random_fluctuation_perc is the primary driver,
            # and target_daily_perc_change nudges it.
            # Or, the target_daily_perc_change is the base, and random_fluctuation_perc is noise around it.
            # Let's use the latter:
            final_daily_perc_change = target_daily_perc_change + random_fluctuation_perc

            # Cap extreme changes to avoid totally unrealistic jumps, e.g. +/- 15% in a day unless it's the last day adjustment
            final_daily_perc_change = max(-15, min(15, final_daily_perc_change))

            # On the very last day before the next anchor, ensure we hit the anchor value
            # Check if the *next* business day is the anchor OR if we are at the end of the list for this period
            is_last_generated_day_before_anchor = False
            if steps_remaining_in_period == 1 and next_anchor_date <= end_date_overall + datetime.timedelta(days=1): # Check if this is the final step to reach an anchor
                 # If this is the last step to reach val_next_anchor
                if current_processing_val > 0: # Avoid division by zero
                    final_daily_perc_change = ((val_next_anchor / current_processing_val) - 1) * 100
                elif val_next_anchor > 0 : # if current is zero but target is not
                    final_daily_perc_change = 10 # Arbitrary jump if current is zero
                else:
                    final_daily_perc_change = 0 # if both are zero or target is zero
                is_last_generated_day_before_anchor = True
                # print(f"Adjusting for anchor: {day_to_process} to hit {val_next_anchor} from {current_processing_val}")


            current_processing_val *= (1 + final_daily_perc_change / 100)
            
            # Ensure value doesn't go below a certain floor (e.g., 0.01 if it's like a stock price)
            current_processing_val = max(0.01, current_processing_val)
            
            is_already_added = any(d[0] == day_to_process for d in all_generated_data)
            if not is_already_added:
                all_generated_data.append((day_to_process, current_processing_val))
                # print(f"Fluct Day: {day_to_process.strftime('%Y.%m.%d')}\t{current_processing_val:.2f}\t(Target%: {target_daily_perc_change:.2f}, Rand%: {random_fluctuation_perc:.2f}, Final%: {final_daily_perc_change:.2f})")
            last_value = current_processing_val

        # After processing a period, set current_date and last_value for the next anchor
        current_date = next_anchor_date
        if current_date <= end_date_overall: # Only if the anchor itself is within our generation range
            if not (current_date.weekday() >=5 or current_date in us_holidays): # If anchor day is a business day
                is_already_added = any(d[0] == current_date for d in all_generated_data)
                # If it was the last day adjusted, its value might be slightly off due to float precision,
                # so explicitly set it to the anchor value.
                # Or if it's an anchor that wasn't the "last adjusted day".
                
                # Remove if already added with a slightly different fluctuated value
                all_generated_data = [d for d in all_generated_data if d[0] != current_date]
                all_generated_data.append((current_date, val_next_anchor))
                # print(f"Anchor Value Set: {current_date.strftime('%Y.%m.%d')}\t{val_next_anchor:.2f}")
                last_value = val_next_anchor


    # Sort data by date as items might be appended out of strict order due to anchor handling
    all_generated_data.sort(key=lambda x: x[0])
    
    # Deduplicate (in case an anchor day was added twice with slightly different float values then corrected)
    final_data_dict = {}
    for date_val, num_val in all_generated_data:
        final_data_dict[date_val] = num_val # Keeps the last one, which should be the corrected anchor if any
    
    final_sorted_data = sorted(final_data_dict.items())


    # Write to CSV
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    output_filename = os.path.join(output_dir, "generated_financial_data.csv")
    
    with open(output_filename, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile, delimiter='\t')
        writer.writerow(["date", "value"]) # Header
        for data_date, data_value in final_sorted_data:
            if data_date <= end_date_overall: # Ensure we don't write past the requested end date
                 writer.writerow([data_date.strftime('%Y.%m.%d'), f"{data_value:.2f}"])
    
    print(f"CSV file generated at: {output_filename}")
    return output_filename

# --- User Provided Data ---
anchor_data_input = """
2025.1.1	1097.86
2024.1.1	3537.86
2023.1.1	17.86
2022.1.1	31635.72
2021.1.1	30065.72
2020.1.1	30065.72
2019.1.1	104977.86
2018.1.1	57167.86
2017.1.1	40267.86
2016.1.1	40267.86
2015.1.1	40267.86
"""

# --- Configuration ---
# Dates are inclusive
overall_start_dt = datetime.date(2015, 1, 1)
overall_end_dt = datetime.date(2025, 5, 23)
output_directory = "/Users/yanzhang/Downloads" # As requested

# --- Generate Data ---
if __name__ == "__main__":
    # Make sure the output directory is valid for your system.
    # If "/Users/yanzhang/Downloads" doesn't exist or you don't have write permission,
    # this will fail. Change it to a suitable path if necessary.
    # For example, for a general case:
    # output_directory = os.path.join(os.path.expanduser("~"), "Downloads") 
    # Or simply:
    # output_directory = "." # To save in the same directory as the script

    # Check if the specified output directory exists, if not, try a default
    if not os.path.exists(output_directory) or not os.path.isdir(output_directory):
        print(f"Warning: Output directory '{output_directory}' not found or not a directory.")
        # Fallback to user's Downloads folder if possible, otherwise current directory
        fallback_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        if os.path.exists(fallback_dir) and os.path.isdir(fallback_dir):
            output_directory = fallback_dir
            print(f"Using fallback directory: {output_directory}")
        else:
            output_directory = "." # Current directory
            print(f"Using current directory as fallback: {os.path.abspath(output_directory)}")


    generated_file = generate_financial_data(overall_start_dt, overall_end_dt, anchor_data_input, output_directory)
    # You can add further processing here if needed, e.g., loading the CSV with pandas to verify
    # import pandas as pd
    # df = pd.read_csv(generated_file, sep='\t')
    # print(df.head())
    # print(df.tail())
    # print(f"Number of rows generated: {len(df)}")