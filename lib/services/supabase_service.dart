import 'package:supabase_flutter/supabase_flutter.dart';
import '../models/job_model.dart';

class SupabaseService {
  final SupabaseClient _supabase = Supabase.instance.client;

  Future<List<Job>> fetchActiveJobs() async {
    final DateTime today = DateTime.now();
    final String todayString =
        '${today.year.toString().padLeft(4, '0')}-${today.month.toString().padLeft(2, '0')}-${today.day.toString().padLeft(2, '0')}';

    final List<dynamic> response = await _supabase
        .from('jobs')
        .select()
        .gte('last_date', todayString)
        .order('last_date', ascending: true);

    return response.map((json) => Job.fromJson(json)).toList();
  }
}