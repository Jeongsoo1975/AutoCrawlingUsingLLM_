# utils/excel_writer.py
import pandas as pd
from config import settings
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class DataWriter:
    def __init__(self):
        if not os.path.exists(settings.OUTPUT_DIR):
            os.makedirs(settings.OUTPUT_DIR)
            logger.info(f"Created output directory: {settings.OUTPUT_DIR}")

    def save_data(self, data: list, filename_prefix="scraped_data"):
        if not data:
            logger.warning("No data provided to save.")
            return None

        try:
            df = pd.DataFrame(data)

            # Ensure all desired columns are present, fill with NA if missing
            ordered_columns = ['source_keyword'] + settings.DATA_FIELDS_TO_EXTRACT
            df = df.reindex(columns=ordered_columns)

            timestamp = datetime.now().strftime(settings.FILE_TIMESTAMP_FORMAT)
            
            # Check output format setting
            output_format = getattr(settings, 'OUTPUT_FORMAT', 'excel').lower()
            
            if output_format == 'csv':
                filename = f"{filename_prefix}_{timestamp}.csv"
                filepath = os.path.join(settings.OUTPUT_DIR, filename)
                df.to_csv(filepath, index=False, encoding='utf-8-sig')
                logger.info(f"Data successfully saved to CSV: {filepath}")
            else:
                filename = f"{filename_prefix}_{timestamp}.xlsx"
                filepath = os.path.join(settings.OUTPUT_DIR, filename)
                df.to_excel(filepath, index=False, engine='openpyxl')
                logger.info(f"Data successfully saved to Excel: {filepath}")
            
            return filepath
        except Exception as e:
            logger.error(f"Failed to save data: {e}")
            return None
    
    # Backward compatibility
    def save_to_excel(self, data: list, filename_prefix="scraped_data"):
        """Backward compatibility method"""
        return self.save_data(data, filename_prefix)