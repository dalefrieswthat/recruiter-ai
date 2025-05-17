import React, { useState } from 'react';
import { ChakraProvider, Box, VStack, Heading, Text, useToast } from '@chakra-ui/react';
import { FileUploader } from './components/FileUploader';
import { AnalysisResults } from './components/AnalysisResults';
import { LoadingSpinner } from './components/LoadingSpinner';
import { RecruiterAgent } from './components/RecruiterAgent';
import { DataVisualization } from './components/DataVisualization';

function App() {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const toast = useToast();

  const handleFileUpload = async (file) => {
    setLoading(true);
    
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('http://localhost:8000/api/analyze', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Analysis failed');
      }

      const data = await response.json();
      setResults(data);
      
      // Log the results to console for debugging
      console.log('Analysis results:', data);
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message,
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <ChakraProvider>
      <Box minH="100vh" bg="gray.50" py={10}>
        <VStack spacing={8} maxW="1200px" mx="auto" px={4}>
          <Heading as="h1" size="2xl" color="blue.600">
            Recruiter AI Platform
          </Heading>
          <Text fontSize="xl" color="gray.600" textAlign="center">
            Upload a resume to get AI-powered candidate analysis, interview questions, and scheduling recommendations.
          </Text>

          <FileUploader onFileUpload={handleFileUpload} />

          {loading && <LoadingSpinner />}

          {results && (
            <>
              {/* Data visualization */}
              <DataVisualization data={results} />
              
              {/* Analysis results */}
              <AnalysisResults results={results} />
            </>
          )}
        </VStack>
        
        {/* Always render the RecruiterAgent when results are available */}
        {results && <RecruiterAgent analysisResults={results} />}
      </Box>
    </ChakraProvider>
  );
}

export default App; 