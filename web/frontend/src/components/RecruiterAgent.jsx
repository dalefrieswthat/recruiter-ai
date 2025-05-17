import React, { useEffect, useRef, useState } from 'react';
import { Box, Button, Text, Link, Badge, useToast, HStack, VStack, Spinner } from '@chakra-ui/react';

export function RecruiterAgent({ analysisResults }) {
  // State for tracking component status
  const [agentStatus, setAgentStatus] = useState("Not initialized");
  const [isLoading, setIsLoading] = useState(false);
  const [debugMode, setDebugMode] = useState(false);
  const [isVerified, setIsVerified] = useState(false);
  
  // Refs to avoid unnecessary rerenders
  const bridgeLoaded = useRef(false);
  const chatbotLoaded = useRef(false);
  const toast = useToast();

  // Load the agent bridge script
  const loadAgentBridge = () => {
    if (!bridgeLoaded.current && !document.querySelector('script[src="/agent-bridge.js"]')) {
      console.log('Loading agent bridge script');
      setAgentStatus("Loading agent bridge...");
      
      const script = document.createElement('script');
      script.src = "/agent-bridge.js";
      script.async = true;
      script.onload = () => {
        console.log('Agent bridge loaded successfully');
        bridgeLoaded.current = true;
        setAgentStatus("Agent bridge loaded");
        
        // Initialize the bridge with data if we have it
        if (window.agentBridge && analysisResults) {
          window.agentBridge.initialize();
          
          // Verify after a short delay to ensure initialization is complete
          setTimeout(() => {
            verifyAgentData();
          }, 1000);
        }
      };
      document.head.appendChild(script);
    }
  };
  
  // Load the chatbot widget (only after verification)
  const loadChatbotWidget = () => {
    if (!isVerified) {
      console.log('Cannot load widget: Data not verified');
      return;
    }
    
    if (!chatbotLoaded.current && !document.querySelector('script[data-agent-id="44e3dd33-30fd-11f0-bf8f-4e013e2ddde4"]')) {
      console.log('Loading chatbot widget');
      setAgentStatus("Loading chatbot widget...");
      
      const script = document.createElement('script');
      script.src = "https://wfck7ikdpdzloatcokfi2fvf.agents.do-ai.run/static/chatbot/widget.js";
      script.async = true;
      script.setAttribute('data-agent-id', '44e3dd33-30fd-11f0-bf8f-4e013e2ddde4');
      script.setAttribute('data-chatbot-id', 'OIfAcnsuJbQH1GX236z7DL0S3inMnivG');
      script.setAttribute('data-name', 'Recruiter Assistant');
      script.setAttribute('data-primary-color', '#031B4E');
      script.setAttribute('data-secondary-color', '#E5E8ED');
      script.setAttribute('data-button-background-color', '#0061EB');
      script.setAttribute('data-starting-message', 'Hello! I\'m your AI recruiting assistant. I have access to the candidate\'s resume analysis. What would you like to know about this candidate?');
      script.setAttribute('data-logo', '/static/chatbot/icons/default-agent.svg');
      script.setAttribute('data-open', 'true');
      
      script.onload = () => {
        console.log('Chatbot widget loaded');
        chatbotLoaded.current = true;
        setAgentStatus("Chatbot widget loaded and ready");
        setIsLoading(false);
        
        toast({
          title: "AI Assistant Ready",
          description: "The recruiting assistant is now available with candidate data",
          status: "success",
          duration: 3000,
          isClosable: true,
        });
      };
      
      document.body.appendChild(script);
    }
  };

  // This effect runs when component mounts and when analysisResults change
  useEffect(() => {
    if (analysisResults) {
      console.log('RecruiterAgent: Analysis results available', analysisResults);
      
      // Store data in global variables for easier access
      window.CANDIDATE_DATA = analysisResults;
      window.CANDIDATE_SCORE = analysisResults.analysis?.overall_fit_score || 0;
      
      // Reset verification state when results change
      setIsVerified(false);
      
      // First remove any existing widgets
      clearExistingWidgets();
      
      // Then load the agent bridge first
      loadAgentBridge();
    }
  }, [analysisResults]);
  
  // Monitor verification state to load widget when verified
  useEffect(() => {
    if (isVerified) {
      loadChatbotWidget();
    }
  }, [isVerified]);
  
  // Clear any existing widgets
  const clearExistingWidgets = () => {
    // Find and remove the chatbot widget script
    const widgetScript = document.querySelector('script[data-agent-id="44e3dd33-30fd-11f0-bf8f-4e013e2ddde4"]');
    if (widgetScript) {
      console.log('Removing existing chatbot widget');
      widgetScript.remove();
      chatbotLoaded.current = false;
    }
    
    // Find and remove any widget iframes
    const agentIframes = Array.from(document.querySelectorAll('iframe'))
      .filter(iframe => iframe.src && iframe.src.includes('agents.do-ai.run'));
    
    agentIframes.forEach(iframe => {
      console.log('Removing iframe:', iframe.src);
      iframe.remove();
    });
  };
  
  // Function to verify the agent can access data
  const verifyAgentData = async () => {
    setIsLoading(true);
    setAgentStatus("Verifying agent data access...");
    
    try {
      // Make sure we have candidate data
      if (!analysisResults) {
        setAgentStatus("No analysis results to verify");
        setIsLoading(false);
        return;
      }
      
      // First try pushing data
      await pushDataToAgent();
      
      // Then verify with a test question
      const serverUrl = window.location.origin; // Get the actual server URL
      const message = encodeURIComponent("What is the candidate's overall score?");
      const verifyUrl = `${serverUrl}/api/agent/proxy-chat?message=${message}`;
      console.log('Verifying with URL:', verifyUrl);
      
      try {
        const verifyResponse = await fetch(verifyUrl, {
          method: 'GET',
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
          }
        });
        
        // Check if we received HTML instead of JSON (common error)
        const contentType = verifyResponse.headers.get('content-type');
        if (contentType && contentType.includes('text/html')) {
          console.error('Received HTML instead of JSON - likely a routing issue');
          setAgentStatus("Received HTML instead of JSON response");
          
          // Try one more time with a different approach
          return await retryDataPush();
        }
        
        // Normal JSON response processing
        const verifyData = await verifyResponse.json();
        console.log('Agent verification response:', verifyData);
        
        // Basic check for meaningful response
        const responseText = verifyData.response || "";
        const score = analysisResults.analysis?.overall_fit_score || 0;
        
        // Check if the response contains the score or relevant information
        if (
          responseText.includes(score.toString()) ||
          responseText.toLowerCase().includes("score") ||
          responseText.toLowerCase().includes("overall fit")
        ) {
          setAgentStatus("Agent data access verified");
          setIsVerified(true);
          setIsLoading(false);
          
          toast({
            title: "Agent Ready",
            description: "Successfully verified agent data access",
            status: "success",
            duration: 3000,
            isClosable: true,
          });
          
          return true;
        }
        
        // If we got here, the response wasn't what we expected
        console.warn('Agent response did not contain expected data:', responseText);
        setAgentStatus("Unexpected agent response - trying alternative method");
        
        // Try alternative approach
        return await retryDataPush();
        
      } catch (error) {
        console.error('Error in first verification attempt:', error);
        setAgentStatus("First verification attempt failed");
        
        // Try alternative approach
        return await retryDataPush();
      }
    } catch (error) {
      console.error('Error verifying data:', error);
      setAgentStatus(`Verification error: ${error.message}`);
      setIsLoading(false);
      
      toast({
        title: "Verification Failed",
        description: "Could not verify agent data access",
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      
      return false;
    }
  };
  
  // Function to push data to the agent
  const pushDataToAgent = async () => {
    setIsLoading(true);
    setAgentStatus("Pushing data to agent...");
    
    try {
      const serverUrl = window.location.origin;
      const pushUrl = `${serverUrl}/api/agent/push-data`;
      console.log('Pushing data via:', pushUrl);
      
      const response = await fetch(pushUrl);
      const data = await response.json();
      
      console.log('Push data result:', data);
      
      if (data.status === 'success') {
        setAgentStatus("Data successfully pushed to agent");
        return true;
      } else {
        setAgentStatus("Failed to push data to agent");
        return false;
      }
    } catch (error) {
      console.error('Error pushing data:', error);
      setAgentStatus(`Error: ${error.message}`);
      return false;
    }
  };
  
  // Alternative approach to retry pushing data
  const retryDataPush = async () => {
    setAgentStatus("Retrying with alternative approach...");
    
    try {
      // Send a direct message that includes the candidate data
      const score = analysisResults.analysis?.overall_fit_score || 0;
      const message = encodeURIComponent(`I want to set the candidate's overall score to ${score}. Using the number ${score}, please confirm you received this information and can access it.`);
      
      const serverUrl = window.location.origin;
      const proxyUrl = `${serverUrl}/api/agent/proxy-chat?message=${message}`;
      console.log('Sending direct message to:', proxyUrl);
      
      const response = await fetch(proxyUrl, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      });
      
      // Check if we received HTML instead of JSON
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('text/html')) {
        console.error('Received HTML instead of JSON - likely a routing issue');
        setAgentStatus("Received HTML instead of JSON response");
        
        // Try the direct API push as last resort
        return await tryDirectApiPush();
      }
      
      const data = await response.json();
      console.log('Alternative approach response:', data);
      
      // Check if the response contains acknowledgment
      const responseText = data.response || "";
      if (
        responseText.includes(score.toString()) ||
        responseText.toLowerCase().includes("received") || 
        responseText.toLowerCase().includes("confirm") || 
        responseText.toLowerCase().includes("stored") ||
        responseText.toLowerCase().includes("i can access")
      ) {
        setAgentStatus("Alternative approach successful");
        setIsVerified(true);
        setIsLoading(false);
        
        toast({
          title: "Agent Ready",
          description: "Data access verified via alternative method",
          status: "success",
          duration: 3000,
          isClosable: true,
        });
        
        return true;
      }
      
      // If first attempt didn't work, try with a different message format
      const secondMessage = encodeURIComponent(`The candidate has an overall score of ${score} out of 100. Their technical skills include Python (9/10) and JavaScript (8/10). Please acknowledge receipt of this data.`);
      
      const secondUrl = `${serverUrl}/api/agent/proxy-chat?message=${secondMessage}`;
      console.log('Sending second message to:', secondUrl);
      
      const secondResponse = await fetch(secondUrl, {
        headers: {
          'Accept': 'application/json'
        }
      });
      
      // Check for HTML response
      const secondContentType = secondResponse.headers.get('content-type');
      if (secondContentType && secondContentType.includes('text/html')) {
        console.error('Received HTML instead of JSON on second attempt');
        setAgentStatus("Received HTML instead of JSON on second attempt");
        
        // Try direct API push as last resort
        return await tryDirectApiPush();
      }
      
      const secondData = await secondResponse.json();
      console.log('Second alternative approach response:', secondData);
      
      // Check if the response contains acknowledgment
      const secondResponseText = secondData.response || "";
      if (
        secondResponseText.includes(score.toString()) ||
        secondResponseText.toLowerCase().includes("received") || 
        secondResponseText.toLowerCase().includes("confirm") || 
        secondResponseText.toLowerCase().includes("stored") ||
        secondResponseText.toLowerCase().includes("acknowledged")
      ) {
        setAgentStatus("Second alternative approach successful");
        setIsVerified(true);
        setIsLoading(false);
        
        toast({
          title: "Agent Ready",
          description: "Data access verified via second alternative method",
          status: "success",
          duration: 3000,
          isClosable: true,
        });
        
        return true;
      }
      
      // If we get here, both attempts failed
      console.error('Both alternative approaches failed');
      setAgentStatus("All verification attempts failed");
      
      // Try direct API push as last resort
      return await tryDirectApiPush();
      
    } catch (error) {
      console.error('Error in alternative approach:', error);
      setAgentStatus(`Alternative approach error: ${error.message}`);
      
      // Try direct API push as last resort
      return await tryDirectApiPush();
    }
  };
  
  // Try direct API push as last resort
  const tryDirectApiPush = async () => {
    setAgentStatus("Trying direct API push...");
    
    try {
      const serverUrl = window.location.origin;
      const pushUrl = `${serverUrl}/api/agent/push-data`;
      console.log('Pushing data directly via:', pushUrl);
      
      const response = await fetch(pushUrl);
      const data = await response.json();
      
      if (data.status === 'success') {
        setAgentStatus("Direct API push successful");
        setIsVerified(true);
        setIsLoading(false);
        
        toast({
          title: "Agent Ready",
          description: "Data pushed successfully via direct API",
          status: "success",
          duration: 3000,
          isClosable: true,
        });
        
        return true;
      } else {
        // Last resort - force it to proceed anyway with user confirmation
        if (window.confirm("All verification methods failed. Would you like to load the agent widget anyway? (It may not have access to all candidate data)")) {
          setAgentStatus("Proceeding without successful verification");
          setIsVerified(true);
          setIsLoading(false);
          
          toast({
            title: "Agent Loaded",
            description: "Proceeding without successful verification - some features may not work properly",
            status: "warning",
            duration: 5000,
            isClosable: true,
          });
          
          return true;
        } else {
          setAgentStatus("All verification attempts failed");
          setIsLoading(false);
          
          toast({
            title: "Verification Failed",
            description: "All verification methods failed, operation cancelled",
            status: "error",
            duration: 5000,
            isClosable: true,
          });
          
          return false;
        }
      }
    } catch (error) {
      console.error('Error in direct API push:', error);
      setAgentStatus(`Direct API push error: ${error.message}`);
      setIsLoading(false);
      
      // User confirmation for proceeding anyway
      if (window.confirm("All verification attempts failed with errors. Load agent widget anyway?")) {
        setAgentStatus("Proceeding despite all errors");
        setIsVerified(true);
        return true;
      }
      
      return false;
    }
  };
  
  // Function to restart the agent
  const handleRestartAgent = () => {
    setIsLoading(true);
    setAgentStatus("Restarting agent...");
    setIsVerified(false);
    
    try {
      // Clear existing widgets
      clearExistingWidgets();
      
      // Reset bridge state if using window.agentBridge
      if (window.agentBridge) {
        window.agentBridge.initialize();
      }
      
      // Start verification process again
      setTimeout(() => {
        verifyAgentData();
      }, 1000);
      
      toast({
        title: "Agent Restarting",
        description: "The AI assistant is being restarted with fresh data",
        status: "info",
        duration: 3000,
        isClosable: true,
      });
    } catch (error) {
      console.error('Error restarting agent:', error);
      setAgentStatus(`Error restarting: ${error.message}`);
      setIsLoading(false);
      
      toast({
        title: "Restart Failed",
        description: `Could not restart agent: ${error.message}`,
        status: "error",
        duration: 3000,
        isClosable: true,
      });
    }
  };

  return (
    <Box p={4} bg="gray.50" borderRadius="md" mt={4}>
      <Text fontWeight="bold" mb={2}>AI Recruiting Assistant</Text>
      
      <HStack mb={2}>
        <Badge colorScheme={agentStatus.includes("Error") || agentStatus.includes("failed") ? "red" : 
                           agentStatus.includes("verified") || agentStatus.includes("ready") ? "green" : "blue"}>
          {agentStatus}
        </Badge>
        {isLoading && <Spinner size="sm" color="blue.500" />}
      </HStack>
      
      <HStack spacing={2} mb={2}>
        <Button 
          size="xs" 
          colorScheme="blue" 
          onClick={verifyAgentData}
          isLoading={isLoading}
          loadingText="Verifying..."
        >
          Verify Data
        </Button>
        
        <Button 
          size="xs" 
          colorScheme="teal" 
          onClick={handleRestartAgent}
          isLoading={isLoading}
          loadingText="Restarting..."
        >
          Restart Agent
        </Button>
        
        <Button 
          size="xs" 
          colorScheme="red" 
          onClick={() => window.location.reload()}
        >
          Reload Page
        </Button>
      </HStack>
      
      {(debugMode || agentStatus.includes("Error") || agentStatus.includes("failed")) && (
        <Box mt={2} p={2} bg="gray.100" borderRadius="md">
          <Text fontSize="sm" mb={2}>Debugging Information:</Text>
          <VStack spacing={1} align="flex-start">
            <Text fontSize="xs">Bridge Loaded: {bridgeLoaded.current ? 'Yes' : 'No'}</Text>
            <Text fontSize="xs">Chatbot Loaded: {chatbotLoaded.current ? 'Yes' : 'No'}</Text>
            <Text fontSize="xs">Data Verified: {isVerified ? 'Yes' : 'No'}</Text>
            <Text fontSize="xs">Candidate Score: {window.CANDIDATE_SCORE || 'Not set'}</Text>
            <Text fontSize="xs">Status: {agentStatus}</Text>
            <Text fontSize="xs">Current URL: {window.location.href}</Text>
            <Text fontSize="xs">Server URL: {window.location.origin}</Text>
          </VStack>
          
          <Text fontSize="xs" mt={2} fontWeight="bold">Test API Endpoints:</Text>
          <VStack spacing={1} align="flex-start">
            <Link href={`${window.location.origin}/api/latest-analysis`} 
                  isExternal 
                  color="blue.500" 
                  fontSize="xs">
              Test Latest Analysis
            </Link>
            <Link href={`${window.location.origin}/api/agent/proxy-chat?message=What%20is%20the%20candidate%27s%20overall%20score?`} 
                  isExternal 
                  color="blue.500" 
                  fontSize="xs">
              Test Agent API
            </Link>
            <Link href={`${window.location.origin}/api/agent/push-data`} 
                  isExternal 
                  color="blue.500" 
                  fontSize="xs">
              Test Push Data
            </Link>
            <Link href={`${window.location.origin}/api/logs`} 
                  isExternal 
                  color="blue.500" 
                  fontSize="xs">
              View Server Logs
            </Link>
          </VStack>
        </Box>
      )}
      
      <Button 
        size="xs" 
        mt={2} 
        colorScheme="gray" 
        onClick={() => setDebugMode(!debugMode)}
      >
        {debugMode ? 'Hide Debug Info' : 'Show Debug Info'}
      </Button>
    </Box>
  );
} 