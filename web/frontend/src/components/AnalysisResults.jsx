import React from 'react';
import {
  Box,
  VStack,
  Heading,
  Text,
  Grid,
  GridItem,
  Badge,
  List,
  ListItem,
  ListIcon,
} from '@chakra-ui/react';
import { FiCheck, FiClock, FiUser, FiBook } from 'react-icons/fi';

export function AnalysisResults({ results }) {
  const { analysis, interview_questions, interview_schedule, structured_data } = results;

  return (
    <VStack spacing={8} w="100%" align="stretch">
      {/* Overall Analysis */}
      <Box p={6} bg="white" borderRadius="lg" shadow="md">
        <Heading size="md" mb={4}>Candidate Analysis</Heading>
        <Grid templateColumns="repeat(2, 1fr)" gap={6}>
          <GridItem>
            <Text fontWeight="bold">Overall Fit Score</Text>
            <Badge colorScheme="blue" fontSize="lg" p={2}>
              {analysis.overall_fit_score}
            </Badge>
          </GridItem>
          <GridItem>
            <Text fontWeight="bold">Experience Level</Text>
            <Badge colorScheme="green" fontSize="lg" p={2}>
              {analysis.experience_level}
            </Badge>
          </GridItem>
        </Grid>
      </Box>

      {/* Skills Assessment */}
      <Box p={6} bg="white" borderRadius="lg" shadow="md">
        <Heading size="md" mb={4}>Skills Assessment</Heading>
        <Grid templateColumns="repeat(3, 1fr)" gap={4}>
          {analysis.technical_skills && Object.entries(analysis.technical_skills).map(([category, skills]) => (
            <GridItem key={category} colSpan={3}>
              <Text fontWeight="bold" mb={2}>{category}</Text>
              <Grid templateColumns="repeat(3, 1fr)" gap={2}>
                {typeof skills === 'object' && Object.entries(skills).map(([skill, score]) => (
                  <GridItem key={skill}>
                    <Text>{skill}</Text>
                    <Badge colorScheme={score > 7 ? "green" : score > 5 ? "yellow" : "red"} p={2}>
                      {score}/10
                    </Badge>
                  </GridItem>
                ))}
              </Grid>
            </GridItem>
          ))}
        </Grid>
      </Box>

      {/* Interview Questions */}
      <Box p={6} bg="white" borderRadius="lg" shadow="md">
        <Heading size="md" mb={4}>Interview Questions</Heading>
        <Grid templateColumns="repeat(2, 1fr)" gap={6}>
          <GridItem>
            <Text fontWeight="bold" mb={2}>Technical Questions</Text>
            <List spacing={2}>
              {interview_questions.technicalQuestions && interview_questions.technicalQuestions.map((q, i) => (
                <ListItem key={i}>
                  <ListIcon as={FiCheck} color="green.500" />
                  {q}
                </ListItem>
              ))}
            </List>
          </GridItem>
          <GridItem>
            <Text fontWeight="bold" mb={2}>Behavioral Questions</Text>
            <List spacing={2}>
              {interview_questions.behavioralQuestions && interview_questions.behavioralQuestions.map((q, i) => (
                <ListItem key={i}>
                  <ListIcon as={FiUser} color="blue.500" />
                  {q}
                </ListItem>
              ))}
            </List>
          </GridItem>
        </Grid>
      </Box>

      {/* Interview Schedule */}
      <Box p={6} bg="white" borderRadius="lg" shadow="md">
        <Heading size="md" mb={4}>Recommended Interview Schedule</Heading>
        <Grid templateColumns="repeat(2, 1fr)" gap={4}>
          <GridItem>
            <Text fontWeight="bold">Duration</Text>
            <Text>{interview_schedule.recommendedDuration}</Text>
          </GridItem>
          <GridItem>
            <Text fontWeight="bold">Type</Text>
            <Text>{interview_schedule.interviewType}</Text>
          </GridItem>
          <GridItem colSpan={2}>
            <Text fontWeight="bold" mb={2}>Suggested Time Slots</Text>
            <List spacing={2}>
              {interview_schedule.suggestedTimeSlots && interview_schedule.suggestedTimeSlots.map((slot, i) => (
                <ListItem key={i}>
                  <ListIcon as={FiClock} color="purple.500" />
                  {slot}
                </ListItem>
              ))}
            </List>
          </GridItem>
        </Grid>
      </Box>

      {/* Structured Data */}
      <Box p={6} bg="white" borderRadius="lg" shadow="md">
        <Heading size="md" mb={4}>Candidate Information</Heading>
        <Grid templateColumns="repeat(2, 1fr)" gap={6}>
          <GridItem>
            <Text fontWeight="bold">Education</Text>
            <List spacing={2}>
              {structured_data.education && structured_data.education.map((edu, i) => (
                <ListItem key={i}>
                  <ListIcon as={FiBook} color="blue.500" />
                  {edu.degree || "Not specified"}
                </ListItem>
              ))}
            </List>
          </GridItem>
          <GridItem>
            <Text fontWeight="bold">Experience</Text>
            <List spacing={2}>
              {structured_data.experience && structured_data.experience.map((exp, i) => (
                <ListItem key={i}>
                  <ListIcon as={FiUser} color="green.500" />
                  {exp.title} {exp.company ? `at ${exp.company}` : ""} {exp.duration ? `(${exp.duration})` : ""}
                </ListItem>
              ))}
            </List>
          </GridItem>
        </Grid>
      </Box>
    </VStack>
  );
} 