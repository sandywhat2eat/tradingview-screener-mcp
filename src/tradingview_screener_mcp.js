#!/usr/bin/env node

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

class TradingViewScreenerMCPServer {
  constructor() {
    this.server = new Server(
      {
        name: 'tradingview-screener-mcp',
        version: '1.0.0',
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    this.setupToolHandlers();

    // Path configuration
    this.pythonPath = '/root/venv/bin/python3';
    this.projectRoot = path.join(__dirname, '..');
  }

  setupToolHandlers() {
    // List available tools
    this.server.setRequestHandler(ListToolsRequestSchema, async () => {
      return {
        tools: [
          {
            name: 'list_screener_types',
            description: 'List all available TradingView screener types dynamically from Supabase controls table. Shows active screeners (on_off=ON) with descriptions, holding periods, and trade types. Configurations are cached for 5 minutes for optimal performance.',
            inputSchema: {
              type: 'object',
              properties: {},
              required: []
            }
          },
          {
            name: 'list_screener_indices',
            description: 'List all available index filters for TradingView screeners (NIFTY50, NIFTYBANK, NIFTYIT, etc.).',
            inputSchema: {
              type: 'object',
              properties: {},
              required: []
            }
          },
          {
            name: 'fetch_screener_data',
            description: 'Fetch TradingView screener data dynamically configured from Supabase controls table. High-performance data fetching for active screeners (where on_off=ON) with optional index filtering. Screener types are dynamically loaded from database, allowing real-time addition/removal of screeners without code changes.',
            inputSchema: {
              type: 'object',
              properties: {
                screener_type: {
                  type: 'string',
                  description: 'Type of screener from controls table (e.g., momentum_breakout_with_volume, opening_breakouts, gap_&_go_(swing))'
                },
                index_filter: {
                  type: 'string',
                  description: 'Optional index filter (e.g., NIFTYBANK, NIFTYIT, NIFTY50, NIFTYMETAL)'
                }
              },
              required: ['screener_type']
            }
          },
          {
            name: 'get_screener_session_health',
            description: 'Get health status of the persistent TradingView browser session including uptime, cache status, and performance metrics.',
            inputSchema: {
              type: 'object',
              properties: {},
              required: []
            }
          },
          {
            name: 'refresh_screener_session',
            description: 'Force refresh of the TradingView browser session. Use when session becomes unresponsive or needs restart.',
            inputSchema: {
              type: 'object',
              properties: {},
              required: []
            }
          },
          {
            name: 'refresh_screener_config',
            description: 'Refresh screener configurations from Supabase controls table. Forces reload of active screeners (on_off=ON) and updates both local cache and persistent service. Use when database changes are made.',
            inputSchema: {
              type: 'object',
              properties: {},
              required: []
            }
          },
          {
            name: 'get_screener_config',
            description: 'Get current screener configuration showing all active screeners from Supabase controls table. Returns screener details, cache status, and available trading strategies.',
            inputSchema: {
              type: 'object',
              properties: {},
              required: []
            }
          }
        ]
      };
    });

    // Handle tool calls
    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;

      try {
        switch (name) {
          case 'list_screener_types':
            return await this.handleListScreenerTypes(args);
          case 'list_screener_indices':
            return await this.handleListScreenerIndices(args);
          case 'fetch_screener_data':
            return await this.handleFetchScreenerData(args);
          case 'get_screener_session_health':
            return await this.handleGetSessionHealth(args);
          case 'refresh_screener_session':
            return await this.handleRefreshSession(args);
          case 'refresh_screener_config':
            return await this.handleRefreshConfig(args);
          case 'get_screener_config':
            return await this.handleGetConfig(args);
          default:
            throw new Error(`Unknown tool: ${name}`);
        }
      } catch (error) {
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify({ error: error.message }, null, 2)
            }
          ],
          isError: true
        };
      }
    });
  }

  async executeScript(scriptPath, args = []) {
    return new Promise((resolve, reject) => {
      const fullScriptPath = path.join(this.projectRoot, scriptPath);

      const childProcess = spawn(this.pythonPath, [fullScriptPath, ...args], {
        stdio: ['pipe', 'pipe', 'pipe'],
        env: { ...process.env }
      });

      let stdout = '';
      let stderr = '';

      childProcess.stdout.on('data', (data) => {
        stdout += data.toString();
      });

      childProcess.stderr.on('data', (data) => {
        stderr += data.toString();
      });

      childProcess.on('close', (code) => {
        if (code === 0) {
          try {
            const jsonOutput = JSON.parse(stdout);
            resolve(jsonOutput);
          } catch (e) {
            resolve({ output: stdout, stderr });
          }
        } else {
          reject(new Error(`Script failed with code ${code}: ${stderr || stdout}`));
        }
      });

      childProcess.on('error', (error) => {
        reject(new Error(`Failed to execute script: ${error.message}`));
      });
    });
  }

  async handleListScreenerTypes(args) {
    const result = await this.executeScript('python/tradingview_screener_handler.py', [
      'handle_list_screener_types'
    ]);

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(result, null, 2)
        }
      ]
    };
  }

  async handleListScreenerIndices(args) {
    const result = await this.executeScript('python/tradingview_screener_handler.py', [
      'handle_list_screener_indices'
    ]);

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(result, null, 2)
        }
      ]
    };
  }

  async handleFetchScreenerData(args) {
    const scriptArgs = ['handle_fetch_screener_data', '--screener_type', args.screener_type];

    if (args.index_filter) {
      scriptArgs.push('--index_filter', args.index_filter);
    }

    const result = await this.executeScript('python/tradingview_screener_handler.py', scriptArgs);

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(result, null, 2)
        }
      ]
    };
  }

  async handleGetSessionHealth(args) {
    const result = await this.executeScript('python/tradingview_screener_handler.py', [
      'handle_get_screener_session_health'
    ]);

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(result, null, 2)
        }
      ]
    };
  }

  async handleRefreshSession(args) {
    const result = await this.executeScript('python/tradingview_screener_handler.py', [
      'handle_refresh_screener_session'
    ]);

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(result, null, 2)
        }
      ]
    };
  }

  async handleRefreshConfig(args) {
    const result = await this.executeScript('python/tradingview_screener_handler.py', [
      'handle_refresh_screener_config'
    ]);

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(result, null, 2)
        }
      ]
    };
  }

  async handleGetConfig(args) {
    const result = await this.executeScript('python/tradingview_screener_handler.py', [
      'handle_get_screener_config'
    ]);

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(result, null, 2)
        }
      ]
    };
  }

  async run() {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error('TradingView Screener MCP Server running on stdio');
  }
}

const server = new TradingViewScreenerMCPServer();
server.run().catch(console.error);
