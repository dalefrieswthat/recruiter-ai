import React from 'react';
import { Spinner, VStack, Text } from '@chakra-ui/react';

export function LoadingSpinner() {
  return (
    <VStack spacing={4}>
      <Spinner
        thickness="4px"
        speed="0.65s"
        emptyColor="gray.200"
        color="blue.500"
        size="xl"
      />
      <Text color="gray.600">Analyzing resume...</Text>
    </VStack>
  );
} 