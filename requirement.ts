import * as fs from 'fs';
import * as path from 'path';
import * as csv from 'csv-parser';
import * as ObjectsToCsv from 'objects-to-csv';

const DATA_DIR = path.join(__dirname, 'data');
const LOG_FILE = path.join(DATA_DIR, 'trades.csv');

interface Trade {
  time: string;
  symbol: string;
  direction: string;
  tp: number;
  sl: number;
  timeframe: string;
  demand_zone: number;
  supply_zone: number;
  result: string;
}

export async function appendTradeToCSV(trade: Trade) {
  if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });

  let fileExists = fs.existsSync(LOG_FILE);

  const csvWriter = new ObjectsToCsv([trade]);

  if (!fileExists) {
    await csvWriter.toDisk(LOG_FILE, { append: false });
  } else {
    await csvWriter.toDisk(LOG_FILE, { append: true });
  }
}

export async function readTrades(): Promise<Trade[]> {
  return new Promise((resolve, reject) => {
    const trades: Trade[] = [];
    if (!fs.existsSync(LOG_FILE)) resolve(trades);

    fs.createReadStream(LOG_FILE)
      .pipe(csv())
      .on('data', (row) => trades.push(row))
      .on('end', () => resolve(trades))
      .on('error', reject);
  });
  }
