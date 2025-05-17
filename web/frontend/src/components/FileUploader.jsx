import React, { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { Box, Text, VStack, Icon } from '@chakra-ui/react';
import { FiUpload } from 'react-icons/fi';

export function FileUploader({ onFileUpload }) {
  const onDrop = useCallback((acceptedFiles) => {
    if (acceptedFiles.length > 0) {
      onFileUpload(acceptedFiles[0]);
    }
  }, [onFileUpload]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/msword': ['.doc'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx']
    },
    multiple: false
  });

  return (
    <Box
      {...getRootProps()}
      w="100%"
      maxW="600px"
      h="200px"
      border="2px dashed"
      borderColor={isDragActive ? 'blue.400' : 'gray.300'}
      borderRadius="lg"
      bg={isDragActive ? 'blue.50' : 'white'}
      cursor="pointer"
      transition="all 0.2s"
      _hover={{ borderColor: 'blue.400', bg: 'blue.50' }}
    >
      <input {...getInputProps()} />
      <VStack h="100%" justify="center" spacing={4}>
        <Icon as={FiUpload} w={10} h={10} color="blue.500" />
        <Text fontSize="lg" color="gray.600">
          {isDragActive
            ? 'Drop the resume here'
            : 'Drag and drop a resume, or click to select'}
        </Text>
        <Text fontSize="sm" color="gray.500">
          Supports PDF, DOC, and DOCX files
        </Text>
      </VStack>
    </Box>
  );
} 