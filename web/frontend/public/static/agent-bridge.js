// Simplified Agent Bridge for DigitalOcean AI Agent Integration
(function() {
    // Prevent default widget initialization
    window.DO_AGENT_WIDGET = {
        initialized: true,
        sendMessage: () => {
            console.warn('Default widget disabled - using proxy endpoint');
            return null;
        }
    };

    window.agentBridge = {
        initialized: false,
        candidateData: null,

        // Initialize the bridge with candidate data
        initialize: async function() {
            try {
                const response = await fetch('/api/latest-analysis');
                if (!response.ok) {
                    throw new Error(`Failed to get latest analysis: ${response.status}`);
                }
                
                const data = await response.json();
                if (!data || data.status === 'no_analysis') {
                    console.warn('No analysis data available');
                    return false;
                }

                this.candidateData = data;
                
                // Set global variables for compatibility
                window.CANDIDATE_DATA = data;
                window.CANDIDATE_SCORE = data.analysis?.overall_fit_score || 0;
                
                // Push data to agent
                await this.pushDataToAgent();
                
                this.initialized = true;
                
                // Override any existing agent widget
                this.overrideDefaultWidget();
                
                return true;
            } catch (error) {
                console.error('Error initializing agent bridge:', error);
                return false;
            }
        },

        // Override the default widget to ensure proxy usage
        overrideDefaultWidget: function() {
            const widgetScript = document.querySelector('script[src*="agent-widget"]');
            if (widgetScript) {
                widgetScript.remove();
            }
            
            window.DO_AGENT_WIDGET = {
                initialized: true,
                sendMessage: (message) => this.sendMessage(message)
            };
        },

        // Push data to the agent
        pushDataToAgent: async function() {
            try {
                const score = this.candidateData.analysis?.overall_fit_score || 0;
                const message = `I want to set the candidate's overall score to ${score}. Using the number ${score}, please confirm you received this information and can access it.`;
                
                const response = await fetch('/api/agent/proxy-chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Use-Proxy': 'true'
                    },
                    body: JSON.stringify({ 
                        message,
                        useProxy: true,
                        candidateData: this.candidateData
                    })
                });

                if (!response.ok) {
                    throw new Error(`Failed to push data: ${response.status}`);
                }

                const result = await response.json();
                return result.response && result.response.includes(score.toString());
            } catch (error) {
                console.error('Error pushing data to agent:', error);
                return false;
            }
        },

        // Send a chat message to the agent
        sendMessage: async function(message) {
            try {
                const response = await fetch('/api/agent/proxy-chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Use-Proxy': 'true'
                    },
                    body: JSON.stringify({ 
                        message,
                        useProxy: true,
                        candidateData: this.candidateData
                    })
                });

                if (!response.ok) {
                    throw new Error(`Failed to send message: ${response.status}`);
                }

                const data = await response.json();
                return data.response || data.message || 'No response from agent';
            } catch (error) {
                console.error('Error sending message to agent:', error);
                throw error;
            }
        },

        // Get the latest candidate data
        getCandidateData: function() {
            return this.candidateData;
        }
    };

    // Initialize when the script loads if we have candidate data
    if (window.CANDIDATE_DATA) {
        window.agentBridge.initialize().then(success => {
            console.log('Agent bridge initialization:', success ? 'successful' : 'failed');
        });
    }
})(); 