import json
import csv
import os
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
import matplotlib.pyplot as plt
import seaborn as sns
import re
from tqdm import tqdm

# Configuration constants
FITBIT_EXPORT_PATH = "G:/My Drive/Takeout/takeout-20250705T062646Z-1-001/Takeout/Fitbit"
OUTPUT_DIR = "./output"
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB limit
MAX_FILES = 1000  # Limit number of files processed

class FitbitDataAnalyzer:
    def __init__(self, fitbit_folder: str = FITBIT_EXPORT_PATH):
        """
        Initialize the analyzer with Fitbit data
        
        Args:
            fitbit_folder: Path to Fitbit export folder
        """
        self.fitbit_path = self._validate_and_sanitize_path(fitbit_folder)
        self.file_paths = {}  # Store file paths by type
        self.data = {}  # Cache for loaded data
        self.max_file_size = MAX_FILE_SIZE
        self.max_files = MAX_FILES
        self.plots_data = {}  # Store data for plotting
        
    def _validate_and_sanitize_path(self, path: str) -> Path:
        """Validate and sanitize input path to prevent path traversal"""
        if not path or not isinstance(path, str):
            raise ValueError("Invalid path provided")
        
        # Remove any path traversal attempts
        sanitized = re.sub(r'\.\./', '', path)
        sanitized = re.sub(r'\.\.\\', '', sanitized)
        
        # Convert to absolute path and validate
        try:
            abs_path = Path(sanitized).resolve()
            return abs_path
        except Exception as e:
            raise ValueError(f"Invalid path: {e}")
    
    def _is_safe_file(self, file_path: Path) -> bool:
        """Check if file is safe to process"""
        try:
            # Check file size
            if file_path.stat().st_size > self.max_file_size:
                print(f"⚠️  Skipping large file: {file_path.name}")
                return False
            
            # Check file extension
            safe_extensions = {'.json', '.csv', '.txt'}
            if file_path.suffix.lower() not in safe_extensions:
                print(f"⚠️  Skipping unsupported file type: {file_path.name}")
                return False
                
            return True
        except (OSError, IOError):
            return False
    
    def discover_files(self):
        """Discover and catalog available files without loading data"""
        if not self.fitbit_path.exists():
            print("❌ Fitbit folder not found")
            raise FileNotFoundError(f"Fitbit export folder not found: {self.fitbit_path}")
        
        print(f"📁 Discovering files in: {self.fitbit_path}")
        
        file_count = 0
        
        # Discover JSON files
        json_files = []
        for file_path in tqdm(self.fitbit_path.glob("**/*.json"), desc="Scanning JSON files"):
            if file_count >= self.max_files:
                print("⚠️  File limit reached")
                break
                
            if self._is_safe_file(file_path):
                json_files.append(file_path)
                file_count += 1
        
        self.file_paths['json'] = json_files
        print(f"✅ Found {len(json_files)} JSON files")
        
        # Discover CSV files
        csv_files = []
        for file_path in tqdm(self.fitbit_path.glob("**/*.csv"), desc="Scanning CSV files"):
            if file_count >= self.max_files:
                print("⚠️  File limit reached")
                break
                
            if self._is_safe_file(file_path):
                csv_files.append(file_path)
                file_count += 1
        
        self.file_paths['csv'] = csv_files
        print(f"✅ Found {len(csv_files)} CSV files")
        
        return len(json_files) + len(csv_files)
    
    def load_data_by_pattern(self, pattern: str):
        """Load data files that match a specific pattern"""
        if pattern not in self.data:
            self.data[pattern] = []
            
        # Load JSON files matching pattern
        for file_path in self.file_paths.get('json', []):
            if pattern in file_path.stem.lower():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self.data[pattern].append(data)
                except json.JSONDecodeError as e:
                    print(f"❌ Invalid JSON {file_path.name}: {e}")
                except (OSError, IOError) as e:
                    print(f"❌ Access error {file_path.name}: {e}")
        
        # Load CSV files matching pattern
        for file_path in self.file_paths.get('csv', []):
            if pattern in file_path.stem.lower():
                try:
                    df = pd.read_csv(file_path, nrows=100000)  # Limit rows
                    self.data[pattern].append(df)
                except pd.errors.EmptyDataError:
                    print(f"⚠️  Empty CSV: {file_path.name}")
                except (OSError, IOError) as e:
                    print(f"❌ CSV access error {file_path.name}: {e}")
        
        return len(self.data[pattern])
    
    def analyze_steps(self):
        """Analyze step data"""
        print(f"\n🚶 STEP ANALYSIS")
        print("=" * 50)
        
        # Load step data on demand
        step_files = self.load_data_by_pattern('step')
        activity_files = self.load_data_by_pattern('activity')
        
        if not self.data.get('step') and not self.data.get('activity'):
            print("❌ No step data found")
            return
        
        # Process step data
        for pattern in ['step', 'activity']:
            if pattern in self.data and self.data[pattern]:
                for data in self.data[pattern]:
                    
                    if isinstance(data, list):
                        # JSON data
                        df = pd.DataFrame(data)
                        if 'dateTime' in df.columns and 'value' in df.columns:
                            df['date'] = pd.to_datetime(df['dateTime'])
                            df['steps'] = pd.to_numeric(df['value'], errors='coerce')
                            
                            total_steps = df['steps'].sum()
                            avg_steps = df['steps'].mean()
                            max_steps = df['steps'].max()
                            
                            print(f"📊 {pattern}:")
                            print(f"   Total steps: {total_steps:,}")
                            print(f"   Daily average: {avg_steps:,.0f}")
                            print(f"   Daily record: {max_steps:,}")
                            
                            # 10,000 steps goal
                            days_goal = (df['steps'] >= 10000).sum()
                            print(f"   Days with 10K+ steps: {days_goal}/{len(df)} ({days_goal/len(df)*100:.1f}%)")
                            
                            # Store data for plotting
                            self.plots_data['steps'] = {
                                'dates': df['date'],
                                'values': df['steps'],
                                'title': 'Daily Steps',
                                'ylabel': 'Steps'
                            }
                            
                    elif isinstance(data, pd.DataFrame):
                        # CSV data
                        print(f"📊 {pattern}: {len(data)} days of data")
                        if len(data) > 0:
                            print(f"   Columns: {list(data.columns)}")
    
    def analyze_heart_rate(self):
        """Analyze heart rate data"""
        print(f"\n❤️  HEART RATE ANALYSIS")
        print("=" * 50)
        
        hr_keys = [k for k in self.data.keys() if 'heart' in k or 'hr' in k]
        
        if not hr_keys:
            print("❌ No heart rate data found")
            return
        
        for key in hr_keys:
            data = self.data[key]
            
            if isinstance(data, list):
                df = pd.DataFrame(data)
                if 'dateTime' in df.columns and 'value' in df.columns:
                    df['date'] = pd.to_datetime(df['dateTime'])
                    df['bpm'] = pd.to_numeric(df['value'], errors='coerce')
                    
                    avg_hr = df['bpm'].mean()
                    min_hr = df['bpm'].min()
                    max_hr = df['bpm'].max()
                    
                    print(f"📊 {key}:")
                    print(f"   Average heart rate: {avg_hr:.0f} bpm")
                    print(f"   Min: {min_hr:.0f} bpm")
                    print(f"   Max: {max_hr:.0f} bpm")
                    
                    # Heart rate zones (approximate)
                    resting_hr = df['bpm'].quantile(0.1)  # 10% lowest
                    print(f"   Resting heart rate (approx): {resting_hr:.0f} bpm")
                    
                    # Store data for plotting
                    self.plots_data['heart_rate'] = {
                        'dates': df['date'],
                        'values': df['bpm'],
                        'title': 'Heart Rate',
                        'ylabel': 'BPM'
                    }
    
    def analyze_sleep(self):
        """Analyze sleep data"""
        print(f"\n😴 SLEEP ANALYSIS")
        print("=" * 50)
        
        sleep_keys = [k for k in self.data.keys() if 'sleep' in k]
        
        if not sleep_keys:
            print("❌ No sleep data found")
            return
        
        for key in sleep_keys:
            data = self.data[key]
            
            if isinstance(data, list):
                df = pd.DataFrame(data)
                if 'dateOfSleep' in df.columns:
                    df['date'] = pd.to_datetime(df['dateOfSleep'])
                    
                    # Sleep duration
                    if 'timeInBed' in df.columns:
                        # Fix type error by ensuring numeric conversion
                        time_in_bed = pd.to_numeric(df['timeInBed'], errors='coerce')
                        df['sleep_hours'] = time_in_bed / 60.0
                        avg_sleep = df['sleep_hours'].mean()
                        print(f"📊 {key}:")
                        print(f"   Average duration: {avg_sleep:.1f} hours")
                        print(f"   Nights < 7h: {(df['sleep_hours'] < 7).sum()}")
                        print(f"   Nights > 9h: {(df['sleep_hours'] > 9).sum()}")
                        
                        # Store data for plotting
                        self.plots_data['sleep'] = {
                            'dates': df['date'],
                            'values': df['sleep_hours'],
                            'title': 'Sleep Duration',
                            'ylabel': 'Hours'
                        }
                    
                    # Sleep efficiency
                    if 'efficiency' in df.columns:
                        avg_efficiency = df['efficiency'].mean()
                        print(f"   Average efficiency: {avg_efficiency:.1f}%")
                    
                    # Sleep phases
                    sleep_phases = ['wake', 'light', 'deep', 'rem']
                    for phase in sleep_phases:
                        if phase in df.columns:
                            phase_avg = df[phase].mean()
                            print(f"   {phase.title()}: {phase_avg:.0f} min/night")
    
    def analyze_activities(self):
        """Analyze activities and exercises"""
        print(f"\n🏃 ACTIVITY ANALYSIS")
        print("=" * 50)
        
        activity_keys = [k for k in self.data.keys() if any(word in k for word in ['activity', 'exercise', 'workout'])]
        
        if not activity_keys:
            print("❌ No activity data found")
            return
        
        for key in activity_keys:
            data = self.data[key]
            
            if isinstance(data, list):
                df = pd.DataFrame(data)
                print(f"📊 {key}: {len(df)} activities")
                
                if 'activityName' in df.columns:
                    top_activities = df['activityName'].value_counts().head(10)
                    print("   Top activities:")
                    for activity, count in top_activities.items():
                        print(f"   - {activity}: {count}")
                
                if 'calories' in df.columns:
                    total_calories = df['calories'].sum()
                    avg_calories = df['calories'].mean()
                    print(f"   Total calories: {total_calories:,}")
                    print(f"   Calories/activity: {avg_calories:.0f}")
    
    def analyze_calories(self):
        """Analyze calorie data"""
        print(f"\n🔥 CALORIE ANALYSIS")
        print("=" * 50)
        
        calorie_keys = [k for k in self.data.keys() if 'calorie' in k]
        
        if not calorie_keys:
            print("❌ No calorie data found")
            return
        
        for key in calorie_keys:
            data = self.data[key]
            
            if isinstance(data, list):
                df = pd.DataFrame(data)
                if 'dateTime' in df.columns and 'value' in df.columns:
                    df['date'] = pd.to_datetime(df['dateTime'])
                    df['calories'] = pd.to_numeric(df['value'], errors='coerce')
                    
                    total_calories = df['calories'].sum()
                    avg_calories = df['calories'].mean()
                    
                    print(f"📊 {key}:")
                    print(f"   Total calories: {total_calories:,}")
                    print(f"   Daily average: {avg_calories:.0f}")
                    
                    # Store data for plotting
                    self.plots_data['calories'] = {
                        'dates': df['date'],
                        'values': df['calories'],
                        'title': 'Daily Calories',
                        'ylabel': 'Calories'
                    }
    
    def generate_weekly_summary(self):
        """Generate weekly summary"""
        print(f"\n📅 WEEKLY SUMMARY")
        print("=" * 50)
        
        # Find data with dates
        dated_data = {}
        for key, data in self.data.items():
            if isinstance(data, list):
                df = pd.DataFrame(data)
                date_cols = [col for col in df.columns if 'date' in col.lower()]
                if date_cols:
                    dated_data[key] = df
        
        if not dated_data:
            print("❌ No dated data found")
            return
        
        # Weekly analysis
        for key, df in dated_data.items():
            try:
                date_col = [col for col in df.columns if 'date' in col.lower()][0]
                df['date'] = pd.to_datetime(df[date_col])
                df['week'] = df['date'].dt.isocalendar().week
                
                if 'value' in df.columns:
                    weekly_avg = df.groupby('week')['value'].mean()
                    print(f"📊 {key} - Weekly averages:")
                    for week, avg in weekly_avg.tail(4).items():
                        print(f"   Week {week}: {avg:.0f}")
            except:
                continue
    
    def create_plots(self, output_dir: str = OUTPUT_DIR):
        """Create visualization plots for the data"""
        if not self.plots_data:
            print("❌ No data available for plotting")
            return
        
        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # Set up the plotting style
        plt.style.use('default')
        sns.set_palette("husl")
        
        # Create subplots
        n_plots = len(self.plots_data)
        fig, axes = plt.subplots(n_plots, 1, figsize=(12, 4 * n_plots))
        if n_plots == 1:
            axes = [axes]
        
        for i, (key, plot_data) in enumerate(self.plots_data.items()):
            ax = axes[i]
            
            # Create the plot
            ax.plot(plot_data['dates'], plot_data['values'], linewidth=1, alpha=0.8)
            ax.set_title(plot_data['title'], fontsize=14, fontweight='bold')
            ax.set_ylabel(plot_data['ylabel'], fontsize=12)
            ax.set_xlabel('Date', fontsize=12)
            
            # Add grid
            ax.grid(True, alpha=0.3)
            
            # Rotate x-axis labels for better readability
            plt.setp(ax.get_xticklabels(), rotation=45, ha='right')
            
            # Add statistics as text
            mean_val = plot_data['values'].mean()
            max_val = plot_data['values'].max()
            min_val = plot_data['values'].min()
            
            stats_text = f'Mean: {mean_val:.1f}\nMax: {max_val:.1f}\nMin: {min_val:.1f}'
            ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, 
                   verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        plt.tight_layout()
        
        # Save the plot
        plot_path = output_path / "fitbit_analysis_plots.png"
        plt.savefig(plot_path, dpi=300, bbox_inches='tight')
        print(f"📊 Plots saved to: {plot_path}")
        
        # Show the plot
        plt.show()
    
    def export_summary(self, output_file: str = "fitbit_summary.json"):
        """Export data summary"""
        summary = {
            'export_date': datetime.now().isoformat(),
            'files_analyzed': list(self.data.keys()),
            'data_summary': {}
        }
        
        for key, data in self.data.items():
            if isinstance(data, list):
                summary['data_summary'][key] = {
                    'type': 'list',
                    'count': len(data),
                    'sample': data[:2] if len(data) > 0 else []
                }
            elif isinstance(data, pd.DataFrame):
                summary['data_summary'][key] = {
                    'type': 'dataframe',
                    'rows': len(data),
                    'columns': list(data.columns)
                }
        
        output_path = Path(OUTPUT_DIR) / output_file
        output_path.parent.mkdir(exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Summary exported to: {output_path}")
        return output_path
    
    def find_patterns(self):
        """Find patterns in the data"""
        print(f"\n🔍 PATTERN ANALYSIS")
        print("=" * 50)
        
        # Day of week analysis
        for key, data in self.data.items():
            if isinstance(data, list):
                df = pd.DataFrame(data)
                date_cols = [col for col in df.columns if 'date' in col.lower()]
                
                if date_cols and 'value' in df.columns:
                    df['date'] = pd.to_datetime(df[date_cols[0]])
                    df['weekday'] = df['date'].dt.day_name()
                    
                    weekday_avg = df.groupby('weekday')['value'].mean()
                    print(f"📊 {key} - Daily averages:")
                    for day, avg in weekday_avg.items():
                        print(f"   {day}: {avg:.0f}")
                    print()

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Fitbit Data Analyzer')
    parser.add_argument('--steps-only', action='store_true', 
                       help='Run only step analysis (basic test)')
    parser.add_argument('--no-plots', action='store_true',
                       help='Skip creating plots')
    parser.add_argument('--no-export', action='store_true',
                       help='Skip exporting summary')
    parser.add_argument('--path', type=str, default=FITBIT_EXPORT_PATH,
                       help=f'Path to Fitbit export folder (default: {FITBIT_EXPORT_PATH})')
    parser.add_argument('--output-dir', type=str, default=OUTPUT_DIR,
                       help=f'Output directory for results (default: {OUTPUT_DIR})')
    
    return parser.parse_args()

def main():
    print("📊 FITBIT DATA ANALYZER")
    print("=" * 50)
    
    # Parse command line arguments
    args = parse_arguments()
    
    # Use argument values directly
    fitbit_path = args.path
    output_dir = args.output_dir
    
    analyzer = FitbitDataAnalyzer(fitbit_path)
    analyzer.discover_files()
    
    print(f"\n🎯 STARTING ANALYSIS")
    print("=" * 50)
    
    # Run analyses based on arguments
    if args.steps_only:
        print("🔍 Running basic test - steps analysis only")
        analyzer.analyze_steps()
    else:
        # Run all analyses
        analyzer.analyze_steps()
        # analyzer.analyze_heart_rate()
        # analyzer.analyze_sleep()
        # analyzer.analyze_activities()
        # analyzer.analyze_calories()
        # analyzer.generate_weekly_summary()
        # analyzer.find_patterns()
    
    # Create plots unless disabled
    if not args.no_plots:
        analyzer.create_plots(output_dir)
        
    print(f"\n✅ Analysis completed!")
    
    # Export summary unless disabled
    if not args.no_export:
        summary_file = analyzer.export_summary()
        print(f"📄 Summary created: {summary_file}")
        

if __name__ == "__main__":
    main()