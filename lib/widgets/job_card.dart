import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../models/job_model.dart';

class JobCard extends StatelessWidget {
  final Job job;
  final VoidCallback onTap;

  const JobCard({
    Key? key,
    required this.job,
    required this.onTap,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    final dateFormat = DateFormat('dd-MM-yyyy');
    String formattedLastDate;
    try {
      formattedLastDate = dateFormat.format(job.lastDate);
    } catch (e) {
      formattedLastDate = dateFormat.format(DateTime.now().add(Duration(days: 365)));
    }

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Card(
        elevation: 4,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                job.title,
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  color: Color(0xFF1A237E),
                ),
              ),
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 8,
                  vertical: 4,
                ),
                decoration: BoxDecoration(
                  color: Color(0xFF1A237E).withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  job.organization,
                  style: TextStyle(
                    fontSize: 12,
                    color: Color(0xFF1A237E),
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Total Vacancies: ${job.totalVacancies}',
                style: const TextStyle(
                  fontSize: 14,
                  color: Color(0xFF1A237E),
                ),
              ),
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 8,
                  vertical: 4,
                ),
                decoration: BoxDecoration(
                  color: Color(0xFF2E7D32),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  'Last Date: $formattedLastDate',
                  style: const TextStyle(
                    fontSize: 12,
                    color: Colors.white,
                  ),
                ),
              ),
              if (job.officialApplyLink.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(
                  'Apply: ${job.officialApplyLink}',
                  style: const TextStyle(
                    fontSize: 12,
                    color: Color(0xFF1A237E),
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}