import 'package:flutter/material.dart';
import '../models/job_model.dart';
import '../services/supabase_service.dart';
import '../widgets/job_card.dart';
import 'job_detail_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({Key? key}) : super(key: key);

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final SupabaseService _supabaseService = SupabaseService();
  final TextEditingController _searchController = TextEditingController();
  List<Job> _allJobs = [];
  List<Job> _filteredJobs = [];
  bool _isLoading = false;
  String _searchQuery = '';
  String _selectedCategory = 'All';
  final List<String> _categories = [
    'All',
    'Railways',
    'SSC',
    'UPSC',
    'Banking',
    'Defence'
  ];

  @override
  void initState() {
    super.initState();
    _fetchJobs();
  }

  Future<void> _fetchJobs() async {
    setState(() {
      _isLoading = true;
    });
    try {
      final List<Job> jobs = await _supabaseService.fetchActiveJobs();
      setState(() {
        _allJobs = jobs;
        _filteredJobs = jobs;
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _isLoading = false;
      });
      if (mounted && _filteredJobs.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error fetching jobs: $e'),
            backgroundColor: Colors.red,
            action: SnackBarAction(
              label: 'Retry',
              textColor: Colors.white,
              onPressed: _fetchJobs,
            ),
          ),
        );
      }
    }
  }

  void _filterJobs() {
    final String queryLower = _searchQuery.toLowerCase();
    final String selectedCategory = _selectedCategory;

    List<Job> filtered = _allJobs.where((job) {
      final bool matchesSearch = job.title.toLowerCase().contains(queryLower) ||
          job.organization.toLowerCase().contains(queryLower);
      final bool matchesCategory = selectedCategory == 'All' ||
          job.organization == selectedCategory;
      return matchesSearch && matchesCategory;
    }).toList();

    setState(() {
      _filteredJobs = filtered;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0,
        title: const Text(
          'Sarkari Jobs',
          style: TextStyle(
            color: Color(0xFF1A237E),
            fontSize: 20,
            fontWeight: FontWeight.bold,
          ),
        ),
        centerTitle: true,
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16.0),
            child: TextField(
              controller: _searchController,
              decoration: InputDecoration(
                hintText: 'Search by title or organization',
                prefixIcon: const Icon(Icons.search),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: const BorderSide(
                    color: Color(0xFF1A237E),
                  ),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: const BorderSide(
                    color: Color(0xFF1A237E),
                    width: 2,
                  ),
                ),
              ),
              onChanged: (value) {
                setState(() {
                  _searchQuery = value;
                });
                _filterJobs();
              },
            ),
          ),
          SizedBox(
            height: 40,
            child: ListView.builder(
              scrollDirection: Axis.horizontal,
              itemCount: _categories.length,
              itemBuilder: (context, index) {
                final String category = _categories[index];
                final bool isSelected = _selectedCategory == category;
                return Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 4.0,
                  ),
                  child: ChoiceChip(
                    label: Text(category),
                    selected: isSelected,
                    onSelected: (bool selected) {
                      setState(() {
                        _selectedCategory = category;
                      });
                      _filterJobs();
                    },
                    selectedColor: Color(0xFF1A237E).withValues(alpha: 0.2),
                    labelStyle: TextStyle(
                      color: isSelected
                          ? Color(0xFF1A237E)
                          : Colors.grey[600],
                    ),
                    backgroundColor: Colors.grey[100],
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(20),
                    ),
                  ),
                );
              },
            ),
          ),
          Expanded(
            child: _isLoading
                ? const Center(
                    child: CircularProgressIndicator(
                      color: Color(0xFF1A237E),
                    ),
                  )
                : _filteredJobs.isEmpty
                    ? Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            const Icon(
                              Icons.search_off,
                              size: 64,
                              color: Color(0xFF1A237E),
                            ),
                            const SizedBox(height: 16),
                            const Text(
                              'No Active Vacancies Found',
                              style: TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.bold,
                                color: Color(0xFF1A237E),
                              ),
                            ),
                            const SizedBox(height: 8),
                            ElevatedButton(
                              onPressed: _fetchJobs,
                              style: ElevatedButton.styleFrom(
                                backgroundColor: Color(0xFF1A237E),
                                foregroundColor: Colors.white,
                              ),
                              child: const Text('Refresh'),
                            ),
                          ],
                        ),
                      )
                    : ListView.builder(
                        padding: const EdgeInsets.all(8.0),
                        itemCount: _filteredJobs.length,
                        itemBuilder: (context, index) {
                          final Job job = _filteredJobs[index];
                          return Padding(
                            padding: const EdgeInsets.only(bottom: 12.0),
                            child: JobCard(
                              job: job,
                              onTap: () {
                                Navigator.push(
                                  context,
                                  MaterialPageRoute(
                                    builder: (context) =>
                                        JobDetailScreen(job: job),
                                  ),
                                );
                              },
                            ),
                          );
                        },
                      ),
          ),
        ],
      ),
    );
  }
}