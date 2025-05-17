import React, { useEffect, useRef, useState } from 'react';
import { Box, Heading, Text, Spinner } from '@chakra-ui/react';
import * as d3 from 'd3';

// Add scaleRadial function if not available in d3
if (!d3.scaleRadial) {
  d3.scaleRadial = function() {
    var linear = d3.scaleLinear();
    
    function scale(x) {
      return Math.sqrt(linear(x));
    }
    
    scale.domain = function(_) {
      return arguments.length ? (linear.domain(_), scale) : linear.domain();
    };
    
    scale.range = function(_) {
      return arguments.length ? (linear.range(_.map(function(v) { return v * v; })), scale) : linear.range().map(Math.sqrt);
    };
    
    scale.ticks = linear.ticks;
    scale.tickFormat = linear.tickFormat;
    
    return scale;
  };
}

export function DataVisualization({ data }) {
  const chartRef = useRef(null);
  const skillsChartRef = useRef(null);
  const timelineRef = useRef(null);
  const [visualData, setVisualData] = useState(null);
  const [loading, setLoading] = useState(true);

  // Fetch visualization-specific data from the backend
  useEffect(() => {
    if (!data) return;
    
    setLoading(true);
    fetch('http://localhost:8000/api/visualization-data')
      .then(response => {
        if (!response.ok) {
          throw new Error('Failed to fetch visualization data');
        }
        return response.json();
      })
      .then(data => {
        setVisualData(data);
        setLoading(false);
      })
      .catch(error => {
        console.error('Error fetching visualization data:', error);
        // Fallback to using the raw data
        setVisualData({
          skills: processSkillsData(data),
          overall: {
            overall_score: data.analysis?.overall_fit_score || 0,
            experience_level: data.analysis?.experience_level || 'Unknown',
          },
          timeline: []
        });
        setLoading(false);
      });
  }, [data]);

  // Process skills data for visualization (as fallback)
  const processSkillsData = (rawData) => {
    if (!rawData?.analysis?.technical_skills) return [];
    
    const skillsData = [];
    Object.entries(rawData.analysis.technical_skills).forEach(([category, skills]) => {
      if (typeof skills === 'object') {
        Object.entries(skills).forEach(([skill, score]) => {
          skillsData.push({ skill, score, category });
        });
      }
    });
    
    return skillsData;
  };

  // Create radar chart for skills
  useEffect(() => {
    if (!visualData || !skillsChartRef.current || loading) return;
    
    const skillsData = visualData.skills;
    if (skillsData.length === 0) return;
    
    // Clear previous chart
    d3.select(skillsChartRef.current).selectAll("*").remove();
    
    const margin = { top: 50, right: 80, bottom: 50, left: 80 };
    const width = 500 - margin.left - margin.right;
    const height = 400 - margin.top - margin.bottom;
    
    const svg = d3.select(skillsChartRef.current)
      .append("svg")
      .attr("width", width + margin.left + margin.right)
      .attr("height", height + margin.top + margin.bottom)
      .append("g")
      .attr("transform", `translate(${margin.left + width/2},${margin.top + height/2})`);
    
    // Scale for bars
    const x = d3.scaleBand()
      .domain(skillsData.map(d => d.skill))
      .range([0, 2 * Math.PI])
      .padding(0.1);
    
    const y = d3.scaleRadial()
      .domain([0, 10])
      .range([0, Math.min(width, height) / 2]);
    
    // Add bars
    svg.append("g")
      .selectAll("path")
      .data(skillsData)
      .join("path")
      .attr("fill", d => d3.interpolateBlues(d.score / 10))
      .attr("d", d3.arc()
        .innerRadius(0)
        .outerRadius(d => y(d.score))
        .startAngle(d => x(d.skill))
        .endAngle(d => x(d.skill) + x.bandwidth())
        .padAngle(0.01)
        .padRadius(0)
      );
    
    // Add labels
    svg.append("g")
      .selectAll("g")
      .data(skillsData)
      .join("g")
      .attr("text-anchor", d => (x(d.skill) + x.bandwidth() / 2 + Math.PI) % (2 * Math.PI) < Math.PI ? "end" : "start")
      .attr("transform", d => `rotate(${(x(d.skill) + x.bandwidth() / 2) * 180 / Math.PI - 90}) translate(${y(d.score) + 10},0)`)
      .append("text")
      .text(d => d.skill)
      .attr("transform", d => (x(d.skill) + x.bandwidth() / 2 + Math.PI) % (2 * Math.PI) < Math.PI ? "rotate(180)" : "rotate(0)")
      .style("font-size", "10px")
      .attr("alignment-baseline", "middle");
    
    // Add title
    svg.append("text")
      .attr("text-anchor", "middle")
      .attr("transform", "translate(0, -180)")
      .style("font-size", "16px")
      .style("font-weight", "bold")
      .text("Technical Skills");
      
  }, [visualData, loading]);

  // Create overall score gauge chart
  useEffect(() => {
    if (!visualData || !chartRef.current || loading) return;
    
    // Clear previous chart
    d3.select(chartRef.current).selectAll("*").remove();
    
    const margin = { top: 20, right: 20, bottom: 20, left: 20 };
    const width = 300 - margin.left - margin.right;
    const height = 300 - margin.top - margin.bottom;
    
    const svg = d3.select(chartRef.current)
      .append("svg")
      .attr("width", width + margin.left + margin.right)
      .attr("height", height + margin.top + margin.bottom)
      .append("g")
      .attr("transform", `translate(${width/2 + margin.left},${height/2 + margin.top})`);
    
    const radius = Math.min(width, height) / 2;
    
    // Overall fit score gauge
    const score = visualData.overall?.overall_score || 0;
    
    // Create gauge background
    const arcBackground = d3.arc()
      .innerRadius(radius * 0.7)
      .outerRadius(radius)
      .startAngle(-Math.PI / 2)
      .endAngle(Math.PI / 2);
    
    svg.append("path")
      .attr("d", arcBackground)
      .style("fill", "#e0e0e0");
    
    // Create gauge fill based on score
    const arcForeground = d3.arc()
      .innerRadius(radius * 0.7)
      .outerRadius(radius)
      .startAngle(-Math.PI / 2)
      .endAngle(-Math.PI / 2 + (score / 10) * Math.PI);
    
    svg.append("path")
      .attr("d", arcForeground)
      .style("fill", d3.interpolateRgb("#3182ce", "#38A169")(score / 10));
    
    // Add score text
    svg.append("text")
      .attr("text-anchor", "middle")
      .attr("dy", "0.5em")
      .style("font-size", "3em")
      .style("font-weight", "bold")
      .text(score);
    
    svg.append("text")
      .attr("text-anchor", "middle")
      .attr("dy", "3em")
      .style("font-size", "1em")
      .text("Overall Score");
    
    // Add experience level badge
    svg.append("text")
      .attr("text-anchor", "middle")
      .attr("dy", "5em")
      .style("font-size", "1.2em")
      .style("font-weight", "bold")
      .text(visualData.overall?.experience_level || 'Unknown');
    
  }, [visualData, loading]);

  // Create timeline visualization for education and experience
  useEffect(() => {
    if (!visualData || !timelineRef.current || loading || !visualData.timeline || visualData.timeline.length === 0) return;
    
    // Clear previous chart
    d3.select(timelineRef.current).selectAll("*").remove();
    
    const margin = { top: 50, right: 20, bottom: 50, left: 20 };
    const width = 600 - margin.left - margin.right;
    const height = 200 - margin.top - margin.bottom;
    
    const svg = d3.select(timelineRef.current)
      .append("svg")
      .attr("width", width + margin.left + margin.right)
      .attr("height", height + margin.top + margin.bottom)
      .append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);
    
    // Add title
    svg.append("text")
      .attr("x", width / 2)
      .attr("y", -20)
      .attr("text-anchor", "middle")
      .style("font-size", "16px")
      .style("font-weight", "bold")
      .text("Education & Experience Timeline");
    
    // Sort timeline items by start date
    const timelineData = [...visualData.timeline].sort((a, b) => {
      // Handle missing dates - put items without dates at the beginning
      if (!a.startDate) return -1;
      if (!b.startDate) return 1;
      return new Date(a.startDate) - new Date(b.startDate);
    });
    
    // Create time scale
    const startDates = timelineData.map(d => d.startDate ? new Date(d.startDate) : null).filter(Boolean);
    const endDates = timelineData.map(d => d.endDate ? new Date(d.endDate) : new Date()).filter(Boolean);
    
    let timeScale;
    if (startDates.length > 0 && endDates.length > 0) {
      const minDate = d3.min(startDates);
      const maxDate = d3.max(endDates);
      timeScale = d3.scaleTime()
        .domain([minDate, maxDate])
        .range([0, width]);
    } else {
      // Fallback if no valid dates
      timeScale = d3.scaleLinear()
        .domain([0, timelineData.length - 1])
        .range([0, width]);
    }
    
    // Add timeline items
    const itemHeight = 40;
    const itemPadding = 10;
    
    svg.selectAll("rect")
      .data(timelineData)
      .enter()
      .append("rect")
      .attr("x", (d, i) => {
        if (d.startDate) {
          return timeScale(new Date(d.startDate));
        } else {
          return timeScale(i);
        }
      })
      .attr("y", (d, i) => (i % 2) * (itemHeight + itemPadding))
      .attr("width", d => {
        if (d.startDate && d.endDate) {
          return timeScale(new Date(d.endDate)) - timeScale(new Date(d.startDate));
        } else {
          return 100; // Default width if no dates
        }
      })
      .attr("height", itemHeight)
      .attr("rx", 5)
      .attr("ry", 5)
      .style("fill", d => d.type === "education" ? "#3182CE" : "#38A169")
      .style("opacity", 0.7);
      
    // Add labels
    svg.selectAll("text.timeline-label")
      .data(timelineData)
      .enter()
      .append("text")
      .attr("class", "timeline-label")
      .attr("x", (d, i) => {
        if (d.startDate) {
          return timeScale(new Date(d.startDate)) + 5;
        } else {
          return timeScale(i) + 5;
        }
      })
      .attr("y", (d, i) => (i % 2) * (itemHeight + itemPadding) + itemHeight / 2 + 5)
      .style("font-size", "10px")
      .style("fill", "white")
      .style("font-weight", "bold")
      .text(d => {
        const title = d.title || "";
        const org = d.type === "education" ? d.institution : d.company;
        return `${title}${org ? ` - ${org}` : ''}`;
      });
      
  }, [visualData, loading]);

  return (
    <Box p={6} bg="white" borderRadius="lg" shadow="md" mb={6} w="100%">
      <Heading size="md" mb={4}>Candidate Data Visualization</Heading>
      <Text mb={4}>
        Visual representation of the candidate's profile based on resume analysis.
      </Text>
      
      {loading ? (
        <Box display="flex" justifyContent="center" p={10}>
          <Spinner size="xl" />
        </Box>
      ) : (
        <>
          <Box display="flex" flexDirection={["column", "column", "row"]} alignItems="center" justifyContent="space-around" mb={6}>
            <Box ref={chartRef} width="300px" height="300px" />
            <Box ref={skillsChartRef} width="500px" height="400px" overflowX="auto" />
          </Box>
          
          <Box ref={timelineRef} width="100%" height="200px" overflowX="auto" mb={6} />
        </>
      )}
    </Box>
  );
} 